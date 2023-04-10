

import rospy
import math
import tf

from std_msgs.msg import Bool, Float32
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist, Pose2D, PoseStamped, Quaternion

from time import time

class PositionController: 
    def __init__(self, KP, KI, KD):
        self.KP = KP
        self.KD = KD 
        self.KI = KI

        self.time = time()
        self.last_time = time()
        self.delta_time = 0

        self.error = 0
        self.last_error = 0
        self.delta_error = 0

        self.integral = 0
    
    def proporcional(self):

        return self.KP * self.error
    
    def integrative(self): 

        self.integral += self.error * self.delta_time
            #anti wind-up
        if(self.integral > 1.5 or self.integral < -1.5):
            self.integral = 0
        # print(self.integral)
        return self.integral * self.KI

    def derivative(self):
        self.delta_error = self.error - self.last_error

        if(self.delta_error != 0):
            self.delta_error = self.delta_error/self.delta_time
        else:
            self.delta_error = 0
        return self.delta_error*self.KD
            
    def output(self, kp, ki, kd, error):
        self.KP = kp
        self.KI = ki
        self.KD = kd

        self.error = error

        self.time = time()
        self.delta_time = self.time - self.last_time

        if (self.error != 0):
            output = self.proporcional() + self.integrative() + self.derivative()
        else: 
            output = self.proporcional() + self.derivative()
        
        self.last_error = self.error
        self.last_time = self.time

        return output

# ----- constants pid controller -> linear 
KP_linear = 0.5 #0.25
KI_linear = 0.1#0.01
KD_linear = 0 #0

# ----- constants pid controller -> angular 
KP_angular = 1#6.3 #0.5
KI_angular = 0#1
KD_angular = 0#0

# ----- setpoints / goal (x, y, theta)
goal_pose = Pose2D()
goal_pose.x = 0
goal_pose.y = 0
goal_pose.theta = 0
goal_quaternion = Quaternion()

# ----- current robot pose/orientation (x, y, theta)
current_pose = Pose2D()
current_quaternion = Quaternion()

# ----- tolerance
Tolerance_linear = 0.3         # in meters 
Tolerance_angular = math.pi/2     # in rad 
Distance_to_goal = 0           # in meters, for the exit point

# ----- machine states
active_pid = True

# ------ pid config 
angular = PositionController(KP_angular, KI_angular, KD_angular)  
linear = PositionController(KP_linear, KI_linear, KD_linear)    

# ------ publishers 
error_angular_pub = rospy.Publisher("/control/position/debug/angular/error", Float32, queue_size = 10)
error_linear_pub = rospy.Publisher("control/position/debug/linear/error", Float32, queue_size = 10)

# ------ subcribers 
cmd_vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)

# ------ messages 
error_angular_msg = Float32()
error_linear_msg = Float32()

vel_msg = Twist()

def turn_on_controller_callback(msg):
    global active_pid
    active_pid = msg.data

def kp_linear_callback(msg):
    global KP_linear
    KP_linear = msg.data

def ki_linear_callback(msg):
    global KI_linear 
    KI_linear = msg.data

def kd_linear_callback(msg): 
    global KD_linear
    KD_linear = msg.data

def kp_angular_callback(msg):
    global KP_angular 
    KP_angular = msg.data

def kd_angular_callback(msg):
    global KI_angular 
    KI_angular = msg.data 

def ki_angular_callback(msg):
    global KD_angular 
    KD_angular = msg.data

def setpoint_callback(msg): 
    global goal_pose
    goal_pose.x = msg.pose.position.x
    goal_pose.y = msg.pose.position.y 

    goal_quaternion = msg.pose.orientation 
    goal_pose.theta = tf.transformations.euler_from_quaternion([goal_quaternion.x, goal_quaternion.y, goal_quaternion.z, goal_quaternion.w])[2]

def odom_callback(odom_msg): 
    global current_pose
    global current_quaternion 
    global goal_pose

    current_pose.x = odom_msg.pose.pose.position.x
    current_pose.y = odom_msg.pose.pose.position.y 
    current_quaternion = odom_msg.pose.pose.orientation

    # transforma quartenion em angulo de euler, e retira só o valor de yaw. 
    current_pose.theta = tf.transformations.euler_from_quaternion([current_quaternion.x, current_quaternion.y, current_quaternion.z, current_quaternion.w])[2]
    
    # distance to the goal 
    delta_x = goal_pose.x - current_pose.x
    delta_y = goal_pose.y - current_pose.y 

    error_linear = math.hypot(delta_x, delta_y)

    # theta angle to reach the current goal 
    print(delta_x == 0 or delta_y == 0)
    if (delta_x == 0 or delta_y == 0): 
        theta_entrance = 0
    else:
        theta_entrance = math.atan2(delta_x,delta_y) - current_pose.theta

    # ajust signal of the error_linear
    if (goal_pose.x < current_pose.x): 
        error_linear = - error_linear
    
    # if the robot is close enought to the goal, the error angular must consider de exit angle now
    # if (error_linear < Distance_to_goal): 
    #     print("correção theta de saida")
    #     # theta angle for leave de currente goal and go to the next one
    #     theta_exit = goal_pose.theta - current_pose.theta
    # else: 
        # theta_exit = 0
    
    # calcula o ângulo total e ajusta para o intervalo [-pi, pi]
    error_angular = theta_entrance #+ theta_exit

    # error_angular = current_pose.theta + theta_entrance + theta_exit
    # error_angular = math.atan2(math.sin(error_angular), math.cos(error_angular))

    # msg for the error topic 
    error_angular_msg.data = error_angular
    error_linear_msg.data = error_linear
    
    # publish the error
    error_angular_pub.publish(error_angular_msg)
    error_linear_pub.publish(error_linear_msg)

    # while the robot is out the tolerance, compute PID, otherwise, send 0 
    if (abs(error_linear) > Tolerance_linear or abs(error_angular) > Tolerance_angular):
        vel_msg.angular.z = angular.output(KP_angular, KI_angular, KD_angular, error_angular)
        vel_msg.linear.x = linear.output(KP_linear, KI_linear, KD_linear, error_linear)
    else: 
        vel_msg.linear.x = 0.0
        vel_msg.angular.z = 0.0 
        print("no objetivo")

    # publish message if pid is active
    if (active_pid): 
        cmd_vel_pub.publish(vel_msg)

    # debug
    print("CONTROL POSITION NODE -------------------------------------------------")
    print(f"SETPOINT -> x:{goal_pose.x} y:{goal_pose.y} theta:{round(goal_pose.theta,2)}")
    print(f"DELTA -> x:{round(delta_x,2)}  y:{round(delta_y,2)}")
    print(f"THETA -> entrance:{round(theta_entrance,2)}  exit:{round(math.atan2(delta_x,delta_y),2)}")
    print(f"ERROR -> linear:{round(error_linear,2)}  angular:{round(error_angular,2)}")
    print(f"VELOCITY OUTPUT -> linear:{round(vel_msg.linear.x,2)}  angular:{round(vel_msg.angular.z,2)}")
    print("\n")

def controller_position():
    rospy.init_node('position_controller', anonymous=True)

    rospy.Subscriber("/control/on",Bool,turn_on_controller_callback)

    rospy.Subscriber("/odom", Odometry, odom_callback)
    rospy.Subscriber("/goal_manager/goal/current", PoseStamped, setpoint_callback)

    rospy.Subscriber("/control/position/setup/linear/kp", Float32, kp_linear_callback)
    rospy.Subscriber("/control/position/setup/linear/ki", Float32, ki_linear_callback)
    rospy.Subscriber("/control/position/setup/linear/kd", Float32, kd_linear_callback)

    rospy.Subscriber("/control/position/setup/angular/kp", Float32, kp_angular_callback)
    rospy.Subscriber("/control/position/setup/angular/ki", Float32, kd_angular_callback)
    rospy.Subscriber("/control/position/setup/angular/kd", Float32, ki_angular_callback)

    rospy.spin()

if __name__ == '__main__':
    try:
        controller_position()
    except rospy.ROSInterruptException:
        pass