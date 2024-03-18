import argparse

from time import perf_counter
import datetime
import numpy as np
import torch
import torchvision
import zmq
import cv2
import multiprocessing
from ublox_gps import UbloxGps
import serial
import datetime
import pytz
# from utils.datasets import letterbox, LoadImages
from utils.general import  check_img_size, non_max_suppression, scale_coords, set_logging, xyxy2xywh
from models.experimental import attempt_load
from utils.torch_utils import TracedModel,  select_device
import time
import signal
import camera_pb2
import os

# 2 processes will run to collect gps data and run inference 
# detect will get images and run inference then publish gps_time, image_in_time and image when there are objects detected
# gps_logger will get gps time, latitude and longtitude then publish independently and share the gps time to detect process

# create a detect function
def detect(gps_queue, gps_lon_queue, gps_lat_queue, gps_reload_queue):
    weights, img_size, trace = args.weights, args.img_size, args.no_trace
    device = select_device(args.device)
    
    # half precision only supported on CUDA
    half = device.type != "cpu"

    # uncommnet to use model
    # load model
    # model = attempt_load(weights, map_location=device)
    # stride = int(model.stride.max())
    # img_size = check_img_size(img_size, stride)

    # if trace: 
    #     print("tracing model now")
    #     model = TracedModel(model, device, args.img_size)
    
    # if half:
    #     model.half() # half model precision to fp16
    #     print("half model precision applied")

    # # Run once to init model
    # print("init model")
    # with torch.inference_mode():
    #     if device.type != "cpu":
    #         model(torch.zeros(1,3, img_size, img_size).to(device).type_as(next(model.parameters())))
    # print("print init model done")

  

    # prepare zmq context to receive image
    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.connect("tcp://localhost:6969")
    subscriber.setsockopt(zmq.SUBSCRIBE, b"")

    # prepare zmq context to send image and gps data
    sender_context = zmq.Context()
    sender = sender_context.socket(zmq.PUB)
    sender.bind("tcp://*:8000")

    with torch.inference_mode():
        while 1:
            print("waiting for image to come")
            message = subscriber.recv()
            data = camera_pb2.DataMessage()
            data.ParseFromString(message)

            image_data_raw = data.image_data
            exposure_time = data.float1
            gain = data.float2

            print("got image, processing now")

            t0 = perf_counter()
            # record the time at image in to send
            image_in_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"Time: {image_in_time}")
            # record the gps time when image comes in
            # if gps_queue.empty():
            #     print("no gps timestamp yet\n")
            # else:
            gps_timestamp = gps_queue.get()
            gps_lon = gps_lon_queue.get()
            gps_lat = gps_lat_queue.get()

            # image_data = np.frombuffer(image_data_raw, dtype=np.uint8)
            # process image for inference

            # dont run inference for now

            # image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            # height, width, channels = image.shape
            # print(f"get image height: {height}")
            # print(f"get image width: {width}")
            # # model_input_size = (img_size, img_size)
            # # image = cv2.resize(image, model_input_size)
            # image = torch.tensor(image, device=device)
            # image = image.permute(2,0,1)
            # image = image.half() if half else image.float()
            # image /= 255.0 # normalize image
            # image = image.unsqueeze(0)

            # t1 = perf_counter()
            # # get image data and preprocessing done
            # print(f"Image conversion latency: {(t1-t0) * 1e3:.2f}ms")

            # # starting inference
            # t2 = perf_counter()

            # pred = model(image)[0]
            # t3 = perf_counter()
            # print(f"Inference time: {(t2-t3) * 1e3:.2f}ms")

           

            # starting class-aware nms
            # t4 = perf_counter()

            # pred = non_max_suppression(pred, args.conf_threshold, args.iou_thres_class_aware, args.classes, agnostic=False)
            # t5 = perf_counter()
            # print(f"Nms time: {(t4-t5) * 1e3:.2f}ms")

            # send images to zmq port after inference 
            # only send images after inference
            
            # get number of detection
            # det = pred[0]
            # det.cpu().numpy()
            # print(f"number of detections: {det.shape[0]}")

             # inference done
            
            # send images only when objects are detected
            # if det.shape[0] != 0:
            # send only when gps is done reloaded
            if gps_reload_queue.qsize() == 0:
                try:
                    sender.send_pyobj((image_data_raw, gps_timestamp, image_in_time, gps_lon, gps_lat, exposure_time, gain))
                except:
                    print(" cannot send no gps time stamp \n reloading gps")
                    gps_reload_queue.put(True)


# function to get gps data and time
def gps_logger(gps_queue, gps_lon_queue, gps_lat_queue, gps_reload_queue):
    print("running gps_logger thread\n")

    
    context_gps= zmq.Context()
    socket_gps = context_gps.socket(zmq.PUB)
    socket_gps.bind("tcp://*:8001")
    
    port_up = False

    while 1:
        if gps_reload_queue.qsize() > 0:
            gps_reload_queue.get()
            print("reloading gps")
            devices = os.listdir("/dev")
            ACM_devices = [device for device in devices if device.startswith("ttyACM")]

            # clean up old serial port when reloading
            if port_up:
                port.close()
                port_up = False
            try:
                port = serial.Serial(f"/dev/{ACM_devices[0]}", baudrate=38400, timeout=1)
                print(f"Using port: /dev/{ACM_devices[0]} ")
                gps = UbloxGps(port)

                port_up = True
            except:
                print("no device found")
            
        gps_data = gps.geo_coords()
        # timeStamp = parsed_data.iTOW
        # gps_time = ubxhelpers.itow2utc(timeStamp)

        #use system time if gps can't get reading
        # if (parsed_data.lon == 0  and parsed_data.lat ==0):
        #     formatted_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        # else:

        #     # set the original timezone to utc
        #     system_time_combined = datetime.datetime.combine(datetime.date.today(), gps_time)
        #     original_timezone = pytz.timezone('UTC')
        #     utc_gps_time = original_timezone.localize(system_time_combined)

        #     # offset time zone to gmt+8
        #     target_timezone = pytz.timezone('Asia/Shanghai')
        #     gmt8time = utc_gps_time.astimezone(target_timezone)
        #     formatted_time = gmt8time.strftime("%Y-%m-%d %H:%M:%S.%f")
        #     formatted_time = formatted_time[:-3]  # Remove the last three digits (microseconds)

        # print(f"gps_time: {formatted_time}")
        # print(f"lon: {parsed_data.lon}")
        # print(f"lat: {parsed_data.lat}")

        # send gps logs as string
        formatted_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        # socket_gps.send_string(f"{formatted_time} {gps_data.lon} {gps_data.lat}")

        # print("time:", formatted_time)
        # print("lon:", gps_data.lon)
        # print("lat:", gps_data.lat)

        # put time string in queue to send to detect process
        gps_queue.put(formatted_time)
        gps_lon_queue.put(gps_data.lon)
        gps_lat_queue.put(gps_data.lat)
        time.sleep(0.02)

        

def singal_handler(sig, frame):
    print("Received signal:", sig)
    detect_process.terminate()
    gps_logger_process.terminate()

    detect_process.join()
    gps_logger_process.join()
    
    print("Done cleaning up exiting now")
    exit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, default="tiny640.pt", help= "choose model weights to load")
    parser.add_argument("--img_size", type=int, default=640, help="image size to scale to for inference")
    parser.add_argument("--conf_threshold", type=float, default=0.25, help="object detection confidence threshold")
    parser.add_argument("--iou_thres_class_aware", type=float, default=0.3, help="IOU threshold for class-aware NMS.")
    parser.add_argument("--iou_thres_class_agnostic", type=float, default=0.8, help="IOU threshold for class-agnostic NMS, applied after class-aware NMS")
    parser.add_argument("--device", default='0', help="cuda device 0 or cpu")
    parser.add_argument("--save_detects_txt", action="store_true", help="Save image detection logs in a txt file")
    parser.add_argument("--nosave", action="store_true", help="do not save images/ videos after inference" )
    parser.add_argument("--classes", type=int, default=0, help="filter by class")
    parser.add_argument("--no_trace", action="store_true", help="do not trace model")

    args = parser.parse_args()
    print(args)

    # handle kill signals gracefullyphinpython
    signal.signal(signal.SIGINT, singal_handler)
    signal.signal(signal.SIGTERM, singal_handler)

    # start main function here
    gps_queue = multiprocessing.Queue(maxsize=2)
    gps_lon_queue = multiprocessing.Queue(maxsize=2)
    gps_lat_queue = multiprocessing.Queue(maxsize=2)
    gps_reload_queue = multiprocessing.Queue(maxsize=2)

    # init gps queue
    gps_reload_queue.put(True)

    detect_process = multiprocessing.Process(target=detect, args=(gps_queue, gps_lat_queue, gps_lon_queue, gps_reload_queue))
    gps_logger_process = multiprocessing.Process(target=gps_logger, args=(gps_queue, gps_lat_queue, gps_lon_queue, gps_reload_queue))

    gps_logger_process.start()
    
    # wait 4 seconds before starting
    # time.sleep(4)
    detect_process.start()

    while 1:
        time.sleep(1)
