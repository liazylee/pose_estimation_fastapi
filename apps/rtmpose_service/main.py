# RTMPose Estimation Service
# Subscribes to YOLOX detection results and estimates human pose keypoints

# TODO: Implement RTMPose service main loop:
# - Subscribe to yolox_{task_id} topics
# - Load RTMPose model and weights  
# - Process detected bounding boxes for pose estimation
# - Publish keypoints to rtmpose_{task_id} topics
# - Handle multiple concurrent tasks and persons per frame

# TODO: Add pose model configuration and optimization
# TODO: Implement keypoint confidence filtering
# TODO: Add performance monitoring and error handling 