#!/usr/bin/env python

import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
import RPi.GPIO as GPIO
import enum

LINEAR_SPEED_SCALE_FACTOR = 100

# Dutycycle to switch off motors
STOP = 0

class Motor(object):
    """generic parent class for motor classes."""
    pwm_pin = -1
    pwm_obj = None
    max_allowable_dc = 100
    pwm_frequency = 20

    def __init__(self, pwm_pin, max_allowable_dc, pwm_frequency):
        self.pwm_pin = pwm_pin
        self.pwm_frequency = pwm_frequency
        self.max_allowable_dc = max_allowable_dc
        GPIO.setup(pwm_pin, GPIO.OUT, initial=GPIO.LOW)
        self.pwm_obj = GPIO.PWM(pwm_pin, pwm_frequency)
        self.pwm_obj.start(0) #start stopped

    def set_power(self, power):
        """set only the power pwm."""
        if power < 0 or power > 1:
            raise ValueError("set_power can only take a value between 0 and 1.")
        
        # carryover from old script:
        # To achieve linear response use the square of the normalized speeds
        power *= abs(power)
        power *= LINEAR_SPEED_SCALE_FACTOR
        power = min(power, self.max_allowable_dc)
        self.pwm_obj.ChangeDutyCycle(round(power))

    def stop(self):
        self.set_power(STOP)
        

class Motor2Pin(Motor):
    """class to control a motor (through an H-bridge) using 2 pins: pwm and direction."""
    dir_pin = -1
    dir_forward_val = -1
    dir_backward_val = -1

    def __init__(self, pwm_pin, dir_pin, dir_forward_val, max_allowable_dc, pwm_frequency):
        super(Motor2Pin, self).__init__(pwm_pin, max_allowable_dc, pwm_frequency)
        self.dir_pin = dir_pin
        self.dir_forward_val = dir_forward_val
        self.dir_backward_val = GPIO.HIGH if dir_forward_val == GPIO.LOW else GPIO.LOW
        GPIO.setup(dir_pin, GPIO.OUT, initial=dir_forward_val)

    def set(self, power):
        """sets power and direction, using power, a value between -1 (backwards) and 1 (forwards)"""
        if power > 1 or power < -1:
            raise ValueException("set() can only take a value between -1 and 1.")

        self.set_power(abs(power))
        if power > 0: #forwards
            GPIO.output(self.dir_pin, self.dir_forward_val)
        elif power < 0: #backwards
            GPIO.output(self.dir_pin, self.dir_backward_val)


class Motor3Pin(Motor):
    """class to control a motor (through an H-bridge) using 3 pins: pwm, forward, and back."""
    forward_pin = -1
    backward_pin = -1

    def __init__(self, pwm_pin, forward_pin, backward_pin, max_allowable_dc, pwm_frequency):
        super(Motor3Pin, self).__init__(pwm_pin, max_allowable_dc, pwm_frequency)
        self.forward_pin = forward_pin
        self.backward_pin = backward_pin
        GPIO.setup([forward_pin, backward_pin], GPIO.OUT, initial=GPIO.LOW)

    def set(self, power):
        """sets power and direction, using power, a value between -1 (backwards) and 1 (forwards)"""
        if power > 1 or power < -1:
            raise ValueException("set() can only take a value between -1 and 1.")
        
        self.set_power(abs(power))

        if power > 0: #forwards
            GPIO.output(self.forward_pin, GPIO.HIGH)
            GPIO.output(self.backward_pin, GPIO.LOW)
        elif power < 0: #backwards
            GPIO.output(self.forward_pin, GPIO.LOW)
            GPIO.output(self.backward_pin, GPIO.HIGH)
            

class ControlMode(enum.Enum):
    """supported types of control.
    tank: anything similar to a tracked chassis, i.e. controlled with a left speed and
          a right speed only.
    mecanum: a four-wheel standard mecanum chassis."""
    tank = 1
    mecanum = 2


# ========================================================================================================
# CONFIG

# commented out because i don't know what these are for and they aren't used -theo
# 
# ANGULAR_SPEED_SCALE_FACTOR = 1/4    # Inverse of time minimum time to make one revolution
# RADIANS_PER_REVOLUTION = 6.28319

#same with these -theo
#
# w_dist = 0.23       # The separation between the drive wheels
# lwheel_pub = None   # Publisher for left wheel speed
# rwheel_pub = None   # Publisher for right wheel speed

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Maximum allowable dutycycle
MAX_ALLOWABLE_DC = 100

# Hertz
FREQ = 20000

# TODO: [for visibility]
# !!! CONFIGURE THIS PER ROBOT !!!
# actually todo: maybe use a config file of some kind to ensure this isn't run before being configured?
#      it could be dangerous for someone to run this script unconfigured.
motors = {}
#
motors['fl'] = Motor2Pin(15, 24, GPIO.LOW, 100, FREQ)
motors['bl'] = Motor2Pin(23, 14, GPIO.LOW, 100, FREQ)
motors['fr'] = Motor2Pin(27, 18, GPIO.HIGH, 100, FREQ)
motors['br'] = Motor2Pin(22, 17, GPIO.HIGH, 100, FREQ)

# the control mode to be used:
control_mode = ControlMode.mecanum

# ========================================================================================================


def StopMotors():
    """stop all motors"""
    # GPIO.output(dir_pins, GPIO.LOW)
    for motor in motors:
        motors[motor].stop()


def cmd_callback(cmdMessage):
    linear_x = cmdMessage.linear.x
    angular_z = cmdMessage.angular.z
    
    if control_mode == None:
        rospy.logerr("cannot run rpi motor controller, control_mode not set!"
                    + "\nMake sure you have configured the script before use!")
    elif control_mode == ControlMode.tank:
        right_speed = 1.0 * linear_x - angular_z
        left_speed = 1.0 * linear_x + angular_z
        motors['l'].set(left_speed)
        motors['r'].set(right_speed)
    elif control_mode == ControlMode.mecanum:
        fr_speed = cmdMessage.linear.x - cmdMessage.linear.y + angular_z
        fl_speed = cmdMessage.linear.x + cmdMessage.linear.y - angular_z
        bl_speed = cmdMessage.linear.x - cmdMessage.linear.y - angular_z
        br_speed = cmdMessage.linear.x + cmdMessage.linear.y + angular_z

        fr_speed = max(min(fr_speed, 1), -1)
        fl_speed = max(min(fl_speed, 1), -1)
        br_speed = max(min(br_speed, 1), -1)
        bl_speed = max(min(bl_speed, 1), -1)
        
        rospy.loginfo("fr power: " + str(fr_speed))
        rospy.loginfo("fl power: " + str(fl_speed))
        rospy.loginfo("br power: " + str(br_speed))
        rospy.loginfo("bl power: " + str(bl_speed))

        motors['fr'].set(fr_speed)
        motors['fl'].set(fl_speed)
        motors['bl'].set(bl_speed)
        motors['br'].set(br_speed)

    # You should build in a deadman switch, however, the bThereClient already has one

# removed for now since this needs re-implementing for scalable motor count.
# def init_publisher():
    # global lwheel_pub, rwheel_pub
    # lwheel_pub = rospy.Publisher('lwheel_vtarget', Float32, queue_size=10)
    # rwheel_pub = rospy.Publisher('rwheel_vtarget', Float32, queue_size=10)


def init_subscriber():
    rospy.Subscriber('/cmd_vel/teleop', Twist, cmd_callback)


def create_node():
    rospy.init_node('pi_motor_controller', anonymous=False)


if __name__ == '__main__':
    # try:
        # init_publisher()
    # except rospy.ROSInterruptException:
        # pass

    create_node()
    init_subscriber()
    rospy.spin()
    StopMotors()
    GPIO.cleanup()
