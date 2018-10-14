# USAGE
# python detect_drowsiness.py --shape-predictor shape_predictor_68_face_landmarks.dat
# python detect_drowsiness.py --shape-predictor shape_predictor_68_face_landmarks.dat --alarm alarm.wav

# import the necessary packages
from scipy.spatial import distance as dist
from imutils.video import VideoStream
from imutils import face_utils
from threading import Thread
import numpy as np
import argparse
import imutils
import time
import dlib
import cv2
import pyrebase
import yawn
import tensorflow as tf
import label_image
import threading
import time

class RepeatEvery(threading.Thread):
    def __init__(self, interval, func, *args, **kwargs):
        threading.Thread.__init__(self)
        self.interval = interval  # seconds between calls
        self.func = func          # function to call
        self.args = args          # optional positional argument(s) for call
        self.kwargs = kwargs      # optional keyword argument(s) for call
        self.runable = True
    def run(self):
        while self.runable:
            self.func(*self.args, **self.kwargs)
            time.sleep(self.interval)
    def stop(self):
        self.runable = False

config = {
  "apiKey": "AIzaSyBFPAXHOjsn-ODsrSHa9TddDWp5UGhIefw",
  "authDomain": "pickle-f6850.firebaseapp.com",
  "databaseURL": "https://pickle-f6850.firebaseio.com/",
  "storageBucket": "pickle-f6850.appspot.com"
}

firebase = pyrebase.initialize_app(config)
db = firebase.database()

graph = label_image.load_graph("retrained_graph.pb")

def read_tensor_from_image_file(file_name, input_height=299, input_width=299,
				input_mean=0, input_std=255):
  	input_name = "file_reader"
  	output_name = "normalized"
  	file_reader = tf.read_file(file_name, input_name)
  	if file_name.endswith(".png"):
   		image_reader = tf.image.decode_png(file_reader, channels = 3,
                                       	name='png_reader')
  	elif file_name.endswith(".gif"):
   		image_reader = tf.image.decode_jpeg(file_reader, channels = 3,
    name = 'jpeg_reader')
  	elif file_name.endswith(".bmp"):
   		image_reader = tf.image.decode_bmp(file_reader, name='bmp_reader')
  	else:
   		image_reader = tf.image.decode_jpeg(file_reader, channels = 3,
                   	                     	name='jpeg_reader')
  	float_caster = tf.cast(image_reader, tf.float32)
  	dims_expander = tf.expand_dims(float_caster, 0);
  	resized = tf.image.resize_bilinear(dims_expander, [input_height, input_width])
  	normalized = tf.divide(tf.subtract(resized, [input_mean]), [input_std])
  	sess = tf.Session()
  	result = sess.run(normalized)

  	return result

def load_labels(label_file):
	label = []
	proto_as_ascii_lines = tf.gfile.GFile(label_file).readlines()
	for l in proto_as_ascii_lines:
		label.append(l.rstrip())
	return label

def classify(frame):
	cv2.imwrite("tflow.jpg", frame)   
	t = read_tensor_from_image_file("tflow.jpg",
                                224,
                                224,
                                128,
                                128)

	input_name = "import/" + "input"
	output_name = "import/" + "final_result"
	input_operation = graph.get_operation_by_name(input_name)
	output_operation = graph.get_operation_by_name(output_name)

	with tf.Session(graph=graph) as sess:
   		start = time.time()
   		results = sess.run(output_operation.outputs[0],
                      	{input_operation.outputs[0]: t})
	end=time.time()
	results = np.squeeze(results)

	top_k = results.argsort()[-5:][::-1]
	labels = load_labels("retrained_labels.txt")

	print('\nEvaluation time (1-image): {:.3f}s\n'.format(end-start))
	template = "{} (score={:0.5f})"
	for i in top_k:
		#print(template.format(labels[i], results[i]))
		print(labels[i])
		db.child(args["user"]).child("violence").update({"violent_scenario": labels[0].upper()})


    	
def eye_aspect_ratio(eye):
	# compute the euclidean distances between the two sets of
	# vertical eye landmarks (x, y)-coordinates
	A = dist.euclidean(eye[1], eye[5])
	B = dist.euclidean(eye[2], eye[4])

	# compute the euclidean distance between the horizontal
	# eye landmark (x, y)-coordinates
	C = dist.euclidean(eye[0], eye[3])

	# compute the eye aspect ratio
	ear = (A + B) / (2.0 * C)

	# return the eye aspect ratio
	return ear
 
# construct the argument parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-p", "--shape-predictor", default="sp.dat",
	help="path to facial landmark predictor")
ap.add_argument("-w", "--webcam", type=int, default=0,
	help="index of webcam on system")
ap.add_argument("-u", "--user", default="test",
	help="Select user account")
ap.add_argument("-v", "--violence", type=int ,default=0,
	help="0 to disable violence detection, 1 to enable")
args = vars(ap.parse_args())
 
# define two constants, one for the eye aspect ratio to indicate
# blink and then a second constant for the number of consecutive
# frames the eye must be below the threshold for to set off the
# alarm
EYE_AR_THRESH = 0.30
if args["violence"]==1:
	EYE_AR_CONSEC_FRAMES = 20
else:
	EYE_AR_CONSEC_FRAMES = 48
print(str(EYE_AR_CONSEC_FRAMES))

# initialize the frame counter as well as a boolean used to
# indicate if the alarm is going off
COUNTER = 0
# initialize dlib's face detector (HOG-based) and then create
# the facial landmark predictor
print("[INFO] loading facial landmark predictor...")
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(args["shape_predictor"])

# grab the indexes of the facial landmarks for the left and
# right eye, respectively
(lStart, lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(rStart, rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]

# start the video stream thread
print("[INFO] starting video stream thread...")
vs = cv2.VideoCapture(args["webcam"])
time.sleep(1.0)

# loop over frames from the video stream
timeout = time.time() + 30
while True:
	test=0
	# grab the frame from the threaded video file stream, resize
	# it, and convert it to grayscale
	# channels)'
	global frame
	ret, frame = vs.read()
	frame = imutils.resize(frame, width=450)
	gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

	# detect faces in the grayscale frame
	rects = detector(gray, 0)

	if args["violence"]==1:
		if test%2==0:
			classify(frame)
	test = test-1
	''''thread = RepeatEvery(100, classify, frame)
	thread.start()
	thread.join(1000)  # allow thread to execute a while...
	thread.stop()'''

	# loop over the face detections
	for rect in rects:
		# determine the facial landmarks for the face region, then
		# convert the facial landmark (x, y)-coordinates to a NumPy
		# array
		shape = predictor(gray, rect)
		shape = face_utils.shape_to_np(shape)

		# extract the left and right eye coordinates, then use the
		# coordinates to compute the eye aspect ratio for both eyes
		leftEye = shape[lStart:lEnd]
		rightEye = shape[rStart:rEnd]
		leftEAR = eye_aspect_ratio(leftEye)
		rightEAR = eye_aspect_ratio(rightEye)

		# average the eye aspect ratio together for both eyes
		ear = (leftEAR + rightEAR) / 2.0

		# compute the convex hull for the left and right eye, then
		# visualize each of the eyes
		leftEyeHull = cv2.convexHull(leftEye)
		rightEyeHull = cv2.convexHull(rightEye)
		cv2.drawContours(frame, [leftEyeHull], -1, (0, 255, 255), 1)
		cv2.drawContours(frame, [rightEyeHull], -1, (0, 255, 255), 1)

		# check to see if the eye aspect ratio is below the blink
		# threshold, and if so, increment the blink frame counter
		returnValue = (yawn.yawnDetector(frame), 'yawn')
		if returnValue[0]:
			print("Yawn detected!")
            # When everything isdone, release the capture
			#print(returnValue)
			cv2.putText(frame, str(yawn.yawnCounter), (10, 50),
					cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

		if ear < EYE_AR_THRESH:
			COUNTER += 1
			# if the eyes were closed for a sufficient number of
			# then sound the alarm
			if COUNTER >= EYE_AR_CONSEC_FRAMES:
				db.child(args["user"]).child("drowsiness").update({"EAR": ear, "frequentYawn" : yawn.yawnCounter
				,"status" : "YES"})
				cv2.putText(frame, "Sleepy", (10, 30),
					cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
		# otherwise, the eye aspect ratio is not below the blink
		# threshold, so reset the counter and alarm
		else:
			COUNTER = 0

		# draw the computed eye aspect ratio on the frame to help
		# with debugging and setting the correct eye aspect ratio
		# thresholds and frame counters
		cv2.putText(frame, "EAR: {:.2f}".format(ear), (300, 30),
			cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
 
	# show the frame
	cv2.imshow("Frame", frame)
	key = cv2.waitKey(1) & 0xFF
 
	# if the `q` key was pressed, break from the loop
	if key == ord("q"):
		break


# do a bit of cleanup
cv2.destroyAllWindows()
vs.stop()