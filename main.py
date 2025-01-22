import sys
import cv2
import numpy as np
from ctypes import *
from MvCameraControl_class import *
import time

class WideAngleCamera:
    def __init__(self):
        self.cam = None
        self.device_list = None
        # Keep the working ROI settings
        self.width = 1920
        self.height = 1080
        # Optimize for smooth video
        self.exposure_time = 90000.0  # Reduced exposure for faster frame rate
        self.gain = 8.0
        self.frame_rate = 60.0       # Increased target frame rate
        self.last_frame_time = 0     # For FPS calculation
        self.fps = 0

    def configure_camera(self):
        try:
            # Get maximum resolution
            width_max = MVCC_INTVALUE()
            height_max = MVCC_INTVALUE()
            self.cam.MV_CC_GetIntValue("WidthMax", width_max)
            self.cam.MV_CC_GetIntValue("HeightMax", height_max)
            
            # Center the ROI
            offset_x = (width_max.nCurValue - self.width) // 2
            offset_y = (height_max.nCurValue - self.height) // 2

            # Stream configuration for smooth video
            self.cam.MV_CC_SetEnumValue("TriggerMode", 0)          # Off
            self.cam.MV_CC_SetEnumValue("AcquisitionMode", 2)      # Continuous
            
            # Set resolution and ROI
            self.cam.MV_CC_SetIntValue("Width", self.width)
            self.cam.MV_CC_SetIntValue("Height", self.height)
            self.cam.MV_CC_SetIntValue("OffsetX", offset_x)
            self.cam.MV_CC_SetIntValue("OffsetY", offset_y)

            # Performance optimizations
            self.cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_RGB8_Packed)
            self.cam.MV_CC_SetFloatValue("AcquisitionFrameRate", self.frame_rate)
            self.cam.MV_CC_SetFloatValue("ExposureTime", self.exposure_time)
            self.cam.MV_CC_SetFloatValue("Gain", self.gain)

            # Set large packet size for GigE
            packet_size = self.cam.MV_CC_GetOptimalPacketSize()
            if packet_size > 0:
                self.cam.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)
                # Set packet delay for stability
                self.cam.MV_CC_SetIntValue("GevSCPD", 15)

            # Enable stream channel settings
            self.cam.MV_CC_SetEnumValue("StreamBufferHandlingMode", 2)  # NewestFirst
            
            print(f"\nCamera configured for smooth video:")
            print(f"Resolution: {self.width}x{self.height}")
            print(f"Target FPS: {self.frame_rate}")
            print(f"Packet Size: {packet_size}")
            return True

        except Exception as e:
            print(f"Error configuring camera: {str(e)}")
            return False

    def connect_camera(self):
        try:
            deviceList = MV_CC_DEVICE_INFO_LIST()
            tlayerType = MV_GIGE_DEVICE
            ret = MvCamera.MV_CC_EnumDevices(tlayerType, deviceList)
            if ret != 0:
                raise Exception(f"Enum devices failed! ret={ret}")

            if deviceList.nDeviceNum == 0:
                raise Exception("No GigE cameras found!")

            print(f"Found {deviceList.nDeviceNum} GigE camera(s)")

            stDeviceList = cast(deviceList.pDeviceInfo[0], POINTER(MV_CC_DEVICE_INFO)).contents
            self.cam = MvCamera()
            ret = self.cam.MV_CC_CreateHandle(stDeviceList)
            if ret != 0:
                raise Exception(f"Create handle failed! ret={ret}")

            ret = self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != 0:
                raise Exception(f"Open device failed! ret={ret}")

            if self.configure_camera():
                print("Camera connected and configured successfully")
                return True
            return False

        except Exception as e:
            print(f"Error connecting to camera: {str(e)}")
            return False

    def start_streaming(self):
        try:
            stParam = MVCC_INTVALUE()
            memset(byref(stParam), 0, sizeof(MVCC_INTVALUE))
            ret = self.cam.MV_CC_GetIntValue("PayloadSize", stParam)
            if ret != 0:
                raise Exception(f"Get payload size failed! ret={ret}")

            # Start grabbing
            ret = self.cam.MV_CC_StartGrabbing()
            if ret != 0:
                raise Exception(f"Start grabbing failed! ret={ret}")

            data_buf = (c_ubyte * stParam.nCurValue)()
            stFrameInfo = MV_FRAME_OUT_INFO_EX()
            
            print("\nStreaming started")
            print("Controls:")
            print("'q' - Quit")
            print("'s' - Save image")
            print("'e'/'d' - Increase/Decrease exposure")
            print("'g'/'f' - Increase/Decrease gain")
            print("'r'/'t' - Increase/Decrease frame rate")

            while True:
                ret = self.cam.MV_CC_GetOneFrameTimeout(data_buf, stParam.nCurValue, stFrameInfo, 1000)
                if ret == 0:
                    # Calculate FPS
                    current_time = time.time()
                    if self.last_frame_time != 0:
                        self.fps = 1 / (current_time - self.last_frame_time)
                    self.last_frame_time = current_time

                    # Process frame
                    data = np.frombuffer(data_buf, count=int(stFrameInfo.nFrameLen), dtype=np.uint8)
                    
                    if stFrameInfo.enPixelType == PixelType_Gvsp_RGB8_Packed:
                        image = data.reshape((stFrameInfo.nHeight, stFrameInfo.nWidth, 3))
                    else:
                        image = data.reshape((stFrameInfo.nHeight, stFrameInfo.nWidth))
                        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

                    # Add info overlay
                    cv2.putText(image, f"FPS: {self.fps:.1f}", 
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(image, f"Exp: {self.exposure_time:.0f}us", 
                              (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(image, f"Gain: {self.gain:.1f}", 
                              (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    cv2.imshow('Wide Angle Camera', image)

                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    elif key == ord('s'):
                        cv2.imwrite('captured_image.jpg', image)
                        print("Image saved as 'captured_image.jpg'")
                    elif key == ord('e'):
                        self.exposure_time *= 1.1
                        self.cam.MV_CC_SetFloatValue("ExposureTime", self.exposure_time)
                    elif key == ord('d'):
                        self.exposure_time /= 1.1
                        self.cam.MV_CC_SetFloatValue("ExposureTime", self.exposure_time)
                    elif key == ord('g'):
                        self.gain = min(self.gain * 1.1, 15.0)
                        self.cam.MV_CC_SetFloatValue("Gain", self.gain)
                    elif key == ord('f'):
                        self.gain = max(self.gain / 1.1, 0.0)
                        self.cam.MV_CC_SetFloatValue("Gain", self.gain)
                    elif key == ord('r'):
                        self.frame_rate = min(self.frame_rate * 1.1, 60.0)
                        self.cam.MV_CC_SetFloatValue("AcquisitionFrameRate", self.frame_rate)
                    elif key == ord('t'):
                        self.frame_rate = max(self.frame_rate / 1.1, 10.0)
                        self.cam.MV_CC_SetFloatValue("AcquisitionFrameRate", self.frame_rate)

        except Exception as e:
            print(f"Error during streaming: {str(e)}")

        finally:
            self.close_camera()

    def close_camera(self):
        try:
            if self.cam:
                self.cam.MV_CC_StopGrabbing()
                self.cam.MV_CC_CloseDevice()
                self.cam.MV_CC_DestroyHandle()
            cv2.destroyAllWindows()
            print("Camera closed successfully")
        except Exception as e:
            print(f"Error closing camera: {str(e)}")

def main():
    camera = WideAngleCamera()
    if camera.connect_camera():
        camera.start_streaming()

if __name__ == "__main__":
    print("Starting Wide Angle Camera with smooth video...")
    main()