#!/usr/bin/env python3
from cereal import car
from math import fabs

from common.conversions import Conversions as CV
from selfdrive.car import STD_CARGO_KG, create_button_enable_events, create_button_event, scale_rot_inertia, scale_tire_stiffness, gen_empty_fingerprint, get_safety_config
from selfdrive.car.gm.values import CAR, CruiseButtons, CarControllerParams, NO_ASCM
from selfdrive.car.interfaces import CarInterfaceBase

ButtonType = car.CarState.ButtonEvent.Type
EventName = car.CarEvent.EventName
GearShifter = car.CarState.GearShifter
BUTTONS_DICT = {CruiseButtons.RES_ACCEL: ButtonType.accelCruise, CruiseButtons.DECEL_SET: ButtonType.decelCruise,
                CruiseButtons.MAIN: ButtonType.altButton3, CruiseButtons.CANCEL: ButtonType.cancel}


class CarInterface(CarInterfaceBase):  
  @staticmethod
  def get_pid_accel_limits(CP, current_speed, cruise_speed):
    params = CarControllerParams()
    return params.ACCEL_MIN, params.ACCEL_MAX

  # Determined by iteratively plotting and minimizing error for f(angle, speed) = steer.
  @staticmethod
  def get_steer_feedforward_volt(desired_angle, v_ego):
    desired_angle *= 0.02904609
    sigmoid = desired_angle / (1 + fabs(desired_angle))
    return 0.10006696 * sigmoid * (v_ego + 3.12485927)

  @staticmethod
  def get_steer_feedforward_acadia(desired_angle, v_ego):
    desired_angle *= 0.09760208
    sigmoid = desired_angle / (1 + fabs(desired_angle))
    return 0.04689655 * sigmoid * (v_ego + 10.028217)

  def get_steer_feedforward_function(self):
    if self.CP.carFingerprint == CAR.VOLT:
      return self.get_steer_feedforward_volt
    elif self.CP.carFingerprint == CAR.ACADIA:
      return self.get_steer_feedforward_acadia
    else:
      return CarInterfaceBase.get_steer_feedforward_default

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), car_fw=None, disable_radar=False):
    ret = CarInterfaceBase.get_std_params(candidate, fingerprint)
    ret.carName = "gm"
    ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.gm)]
    ret.alternativeExperience = 1 # UNSAFE_DISABLE_DISENGAGE_ON_GAS
    ret.pcmCruise = False  # stock cruise control is kept off
    ret.openpilotLongitudinalControl = True # ASCM vehicles use OP for long
    ret.radarOffCan = False # ASCM vehicles (typically) have radar

    # These cars have been put into dashcam only due to both a lack of users and test coverage.
    # These cars likely still work fine. Once a user confirms each car works and a test route is
    # added to selfdrive/car/tests/routes.py, we can remove it from this list.
    ret.dashcamOnly = candidate in {CAR.CADILLAC_ATS, CAR.HOLDEN_ASTRA, CAR.MALIBU, CAR.BUICK_REGAL}

    # Presence of a camera on the object bus is ok.
    # Have to go to read_only if ASCM is online (ACC-enabled cars),
    # or camera is on powertrain bus (LKA cars without ACC).
    
    # Saving this for a rainy day...
    # # Dynamically replace the DBC used based on the magic toggle value
    # params = Params()
    # new_pedal_transform = params.get_bool("GMNewPedalTransform")
    # if (new_pedal_transform):
    #   for c in DBC.keys():
    #     v = DBC[c]
    #     DBC[c] = dbc_dict('gm_global_a_powertrain_bolt_generated', v["radar"], v["chassis"], v["body"])
    # CarInterface.using_new_pedal_transform = new_pedal_transform
    
    # LKAS only - no radar, no long 
    if candidate in NO_ASCM:
      ret.openpilotLongitudinalControl = False
      ret.radarOffCan = True
    
    # TODO: How Do we detect vehicles using stock cam-based ACC?
      #ret.pcmCruise = True
      
    tire_stiffness_factor = 0.444  # not optimized yet

    # Start with a baseline tuning for all GM vehicles. Override tuning as needed in each model section below.
    ret.minSteerSpeed = 7 * CV.MPH_TO_MS
    ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
    ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.2], [0.00]]
    ret.lateralTuning.pid.kf = 0.00004   # full torque for 20 deg at 80mph means 0.00007818594
    ret.steerActuatorDelay = 0.1  # Default delay, not measured yet
    ret.enableGasInterceptor = 0x201 in fingerprint[0]
    # # Check for Electronic Parking Brake
    # TODO: JJS: Add param to cereal
    # ret.hasEPB = 0x230 in fingerprint[0]
    
    # baseline longitudinal tune
    ret.longitudinalTuning.kpBP = [5., 35.]
    ret.longitudinalTuning.kpV = [2.4, 1.5]
    ret.longitudinalTuning.kiBP = [0.]
    ret.longitudinalTuning.kiV = [0.36]

    ret.steerLimitTimer = 0.4
    ret.radarTimeStep = 0.0667  # GM radar runs at 15Hz instead of standard 20Hz
    
    
    
    if ret.enableGasInterceptor:
      ret.openpilotLongitudinalControl = True

    ret.longitudinalTuning.kpBP = [5., 35.]
    ret.longitudinalTuning.kpV = [2.4, 1.5]
    ret.longitudinalTuning.kiBP = [0.]
    ret.longitudinalTuning.kiV = [0.36]

    ret.steerLimitTimer = 0.4
    ret.radarTimeStep = 0.0667  # GM radar runs at 15Hz instead of standard 20Hz

    # supports stop and go, but initial engage must (conservatively) be above 18mph
    ret.minEnableSpeed = 18 * CV.MPH_TO_MS

    if candidate == CAR.VOLT or candidate == CAR.VOLT_NR:
      ret.mass = 1607. + STD_CARGO_KG
      ret.wheelbase = 2.69
      ret.steerRatio = 17.7  # Stock 15.7, LiveParameters
      tire_stiffness_factor = 0.469 # Stock Michelin Energy Saver A/S, LiveParameters
      ret.centerToFront = ret.wheelbase * 0.45 # Volt Gen 1, TODO corner weigh

      ret.lateralTuning.pid.kpBP = [0., 40.]
      ret.lateralTuning.pid.kpV = [0., 0.17]
      ret.lateralTuning.pid.kiBP = [0.]
      ret.lateralTuning.pid.kiV = [0.]
      ret.lateralTuning.pid.kf = 1. # get_steer_feedforward_volt()
      ret.steerActuatorDelay = 0.2

      if ret.enableGasInterceptor:
        #Note: Low speed, stop and go not tested. Should be fairly smooth on highway
        ret.longitudinalTuning.kpBP = [0., 35.0]
        ret.longitudinalTuning.kpV = [0.4, 0.06] 
        ret.longitudinalTuning.kiBP = [0., 35.0] 
        ret.longitudinalTuning.kiV = [0.0, 0.04]
        ret.longitudinalTuning.kf = 0.25
        ret.stoppingDecelRate = 0.8  # reach stopping target smoothly, brake_travel/s while trying to stop
        ret.stopAccel = 0. # Required acceleraton to keep vehicle stationary
        ret.vEgoStopping = 0.5  # Speed at which the car goes into stopping state, when car starts requesting stopping accel
        ret.vEgoStarting = 0.5  # Speed at which the car goes into starting state, when car starts requesting starting accel,
        # vEgoStarting needs to be > or == vEgoStopping to avoid state transition oscillation
        ret.stoppingControl = True

    elif candidate == CAR.MALIBU or candidate == CAR.MALIBU_NR:
      ret.mass = 1496. + STD_CARGO_KG
      ret.wheelbase = 2.83
      ret.steerRatio = 15.8
      ret.centerToFront = ret.wheelbase * 0.4  # wild guess

    elif candidate == CAR.HOLDEN_ASTRA:
      ret.mass = 1363. + STD_CARGO_KG
      ret.wheelbase = 2.662
      # Remaining parameters copied from Volt for now
      ret.centerToFront = ret.wheelbase * 0.4
      ret.steerRatio = 15.7

    elif candidate == CAR.ACADIA or candidate == CAR.ACADIA_NR:
      ret.minEnableSpeed = -1.  # engage speed is decided by pcm
      ret.mass = 4353. * CV.LB_TO_KG + STD_CARGO_KG
      ret.wheelbase = 2.86
      ret.steerRatio = 14.4  # end to end is 13.46
      ret.centerToFront = ret.wheelbase * 0.4
      ret.lateralTuning.pid.kf = 1.  # get_steer_feedforward_acadia()

    elif candidate == CAR.BUICK_REGAL:
      ret.mass = 3779. * CV.LB_TO_KG + STD_CARGO_KG  # (3849+3708)/2
      ret.wheelbase = 2.83  # 111.4 inches in meters
      ret.steerRatio = 14.4  # guess for tourx
      ret.centerToFront = ret.wheelbase * 0.4  # guess for tourx

    elif candidate == CAR.CADILLAC_ATS:
      ret.mass = 1601. + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 15.3
      ret.centerToFront = ret.wheelbase * 0.49

    elif candidate == CAR.ESCALADE_ESV:
      ret.minEnableSpeed = -1.  # engage speed is decided by pcm
      ret.mass = 2739. + STD_CARGO_KG
      ret.wheelbase = 3.302
      ret.steerRatio = 17.3
      ret.centerToFront = ret.wheelbase * 0.49
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[10., 41.0], [10., 41.0]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.13, 0.24], [0.01, 0.02]]
      ret.lateralTuning.pid.kf = 0.000045
      tire_stiffness_factor = 1.0

    elif candidate == CAR.BOLT_NR:
      ret.minEnableSpeed = -1
      ret.minSteerSpeed = 5 * CV.MPH_TO_MS
      ret.mass = 1616. + STD_CARGO_KG
      ret.wheelbase = 2.60096
      ret.steerRatio = 16.8
      ret.steerRatioRear = 0.
      ret.centerToFront = 2.0828 #ret.wheelbase * 0.4 # wild guess
      tire_stiffness_factor = 1.0
      # TODO: Improve stability in turns 
      # still working on improving lateral
      
      # TODO: Should ActuatorDelay be converted to BPV arrays?
      # TODO: Check if the actuator delay changes based on vehicle speed
      ret.steerActuatorDelay = 0.
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[10., 41.0], [10., 41.0]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.18, 0.275], [0.01, 0.021]]
      ret.lateralTuning.pid.kf = 0.0002
      
      
      if ret.enableGasInterceptor:
        #Note: Low speed, stop and go not tested. Should be fairly smooth on highway
        ret.longitudinalTuning.kpBP = [0., 35.0]
        ret.longitudinalTuning.kpV = [0.4, 0.06] 
        ret.longitudinalTuning.kiBP = [0., 35.0] 
        ret.longitudinalTuning.kiV = [0.0, 0.04]
        ret.longitudinalTuning.kf = 0.25
        ret.stoppingDecelRate = 0.8  # reach stopping target smoothly, brake_travel/s while trying to stop
        ret.stopAccel = 0. # Required acceleraton to keep vehicle stationary
        ret.vEgoStopping = 0.5  # Speed at which the car goes into stopping state, when car starts requesting stopping accel
        ret.vEgoStarting = 0.5  # Speed at which the car goes into starting state, when car starts requesting starting accel,
        # vEgoStarting needs to be > or == vEgoStopping to avoid state transition oscillation
        ret.stoppingControl = True

        # You can see how big the changes are with the new approach

        # darknight11's tuning efforts using old pedal transform
        # ret.longitudinalTuning.kpBP = [0., 35]
        # ret.longitudinalTuning.kpV = [0.21, 0.46] 
        # ret.longitudinalTuning.kiBP = [0., 35.] 
        # ret.longitudinalTuning.kiV = [0.22, 0.33]
        # ret.stoppingDecelRate = 0.17  # reach stopping target smoothly, brake_travel/s while trying to stop
        # ret.stopAccel = 0. # Required acceleraton to keep vehicle stationary
        # ret.vEgoStopping = 0.6  # Speed at which the car goes into stopping state, when car starts requesting stopping accel
        # ret.vEgoStarting = 0.6  # Speed at which the car goes into starting state, when car starts requesting starting accel,

    elif candidate == CAR.EQUINOX_NR:
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 3500. * CV.LB_TO_KG + STD_CARGO_KG # (3849+3708)/2
      ret.wheelbase = 2.72 #107.3 inches in meters
      ret.steerRatio = 14.4 # guess for tourx
      ret.steerRatioRear = 0. # unknown online
      ret.centerToFront = ret.wheelbase * 0.4 # wild guess

    elif candidate == CAR.TAHOE_NR:
      ret.minEnableSpeed = -1. # engage speed is decided by pcmFalse
      ret.minSteerSpeed = -1 * CV.MPH_TO_MS
      ret.mass = 5602. * CV.LB_TO_KG + STD_CARGO_KG # (3849+3708)/2
      ret.wheelbase = 2.95 #116 inches in meters
      ret.steerRatio = 16.3 # guess for tourx
      ret.steerRatioRear = 0. # unknown online
      ret.centerToFront = 2.59  # ret.wheelbase * 0.4 # wild guess
      ret.steerActuatorDelay = 0.2
      ret.pcmCruise = True # TODO: see if this resolves cruiseMismatch
      ret.openpilotLongitudinalControl = False # ASCM vehicles use OP for long
      ret.radarOffCan = True # ASCM vehicles (typically) have radar

      # According to JYoung, decrease MAX_LAT_ACCEL if it is understeering
      # friction may need to be increased slowly as well
      # I'm not sure what to do about centering / wandering
      MAX_LAT_ACCEL = 2.5
      ret.lateralTuning.init('torque')
      ret.lateralTuning.torque.useSteeringAngle = True
      ret.lateralTuning.torque.kp = 2.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.kf = 1.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.ki = 0.50 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.friction = 0.1

    elif candidate == CAR.SILVERADO_NR:
      # Thanks skip for the tune!
      ret.minEnableSpeed = -1.
      ret.minSteerSpeed = -1 * CV.MPH_TO_MS
      ret.mass = 2400. + STD_CARGO_KG
      ret.wheelbase = 3.745
      ret.steerRatio = 16.3
      ret.pcmCruise = True # TODO: see if this resolves cruiseMismatch
      ret.centerToFront = ret.wheelbase * .49
      ret.steerActuatorDelay = 0.11
      # ret.lateralTuning.pid.kpBP = [i * CV.MPH_TO_MS for i in [15., 80.]]
      # ret.lateralTuning.pid.kpV = [0.13, 0.23]

      # According to JYoung, decrease MAX_LAT_ACCEL if it is understeering
      # friction may need to be increased slowly as well
      # I'm not sure what to do about centering / wandering
      MAX_LAT_ACCEL = 2.5
      ret.lateralTuning.init('torque')
      ret.lateralTuning.torque.useSteeringAngle = True
      ret.lateralTuning.torque.kp = 2.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.kf = 1.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.ki = 0.50 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.friction = 0.1

      # JJS: just saving previous values for posterity
      # ret.minEnableSpeed = -1. # engage speed is decided by pcm
      # ret.minSteerSpeed = -1 * CV.MPH_TO_MS
      # ret.mass = 2241. + STD_CARGO_KG
      # ret.wheelbase = 3.745
      # ret.steerRatio = 16.3 # Determined by skip # 16.3 # From a 2019 SILVERADO
      # ret.centerToFront = ret.wheelbase * 0.49
      # ret.steerActuatorDelay = 0.11 # Determined by skip # 0.075
      # ret.pcmCruise = True # TODO: see if this resolves cruiseMismatch

    elif candidate == CAR.SUBURBAN:
      ret.minEnableSpeed = -1. # engage speed is decided by pcmFalse
      ret.minSteerSpeed = -1 * CV.MPH_TO_MS
      ret.mass = 2731. + STD_CARGO_KG
      ret.wheelbase = 3.302
      ret.steerRatio = 17.3 # COPIED FROM SILVERADO
      ret.centerToFront = ret.wheelbase * 0.49
      ret.steerActuatorDelay = 0.075
      ret.pcmCruise = True # TODO: see if this resolves cruiseMismatch
      ret.openpilotLongitudinalControl = False # ASCM vehicles use OP for long
      ret.radarOffCan = True # ASCM vehicles (typically) have radar

      # According to JYoung, decrease MAX_LAT_ACCEL if it is understeering
      # friction may need to be increased slowly as well
      # I'm not sure what to do about centering / wandering
      MAX_LAT_ACCEL = 2.0
      ret.lateralTuning.init('torque')
      ret.lateralTuning.torque.useSteeringAngle = True
      ret.lateralTuning.torque.kp = 2.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.kf = 1.0 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.ki = 0.50 / MAX_LAT_ACCEL
      ret.lateralTuning.torque.friction = 0.12

    elif candidate == CAR.BOLT_EUV:
      ret.minEnableSpeed = -1
      ret.minSteerSpeed = 5 * CV.MPH_TO_MS
      ret.mass = 1616. + STD_CARGO_KG
      ret.wheelbase = 2.60096
      ret.steerRatio = 16.8
      ret.steerRatioRear = 0.
      ret.centerToFront = 2.0828 #ret.wheelbase * 0.4 # wild guess
      tire_stiffness_factor = 1.0
      # TODO: Improve stability in turns 
      # still working on improving lateral
      ret.steerActuatorDelay = 0.
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[10., 41.0], [10., 41.0]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.18, 0.275], [0.01, 0.021]]
      ret.lateralTuning.pid.kf = 0.0002
      # ret.steerMaxBP = [10., 25.]
      # ret.steerMaxV = [1., 1.2]
      ret.pcmCruise = True # TODO: see if this resolves cruiseMismatch
      ret.openpilotLongitudinalControl = False # Using Stock ACC
      ret.radarOffCan = True # No Radar
      # Note: No Long tuning as we are using stock long
    

         
    # TODO: get actual value, for now starting with reasonable value for
    # civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront,
                                                                         tire_stiffness_factor=tire_stiffness_factor)

    return ret

  # returns a car.CarState
  def _update(self, c):
    ret = self.CS.update(self.cp, self.cp_loopback, self.cp_body)

    ret.steeringRateLimited = self.CC.steer_rate_limited if self.CC is not None else False

    if self.CS.cruise_buttons != self.CS.prev_cruise_buttons and self.CS.prev_cruise_buttons != CruiseButtons.INIT:
      be = create_button_event(self.CS.cruise_buttons, self.CS.prev_cruise_buttons, BUTTONS_DICT, CruiseButtons.UNPRESS)

      # Suppress resume button if we're resuming from stop so we don't adjust speed.
      if be.type == ButtonType.accelCruise and (ret.cruiseState.enabled and ret.standstill):
        be.type = ButtonType.unknown

      ret.buttonEvents = [be]

    # # From Honda
    # if self.CP.pcmCruise:
    #   # we engage when pcm is active (rising edge)
    #   if ret.cruiseState.enabled and not self.CS.out.cruiseState.enabled:
    #     events.add(EventName.pcmEnable)
    ## above handled in create_common_events
    #   elif not ret.cruiseState.enabled and (c.actuators.accel >= 0. or not self.CP.openpilotLongitudinalControl):
    #     # it can happen that car cruise disables while comma system is enabled: need to
    #     # keep braking if needed or if the speed is very low
    #     if ret.vEgo < self.CP.minEnableSpeed + 2.:
    #       # non loud alert if cruise disables below 25mph as expected (+ a little margin)
    #       events.add(EventName.speedTooLow)
    #     else:
    #       events.add(EventName.cruiseDisabled)
    # if self.CS.CP.minEnableSpeed > 0 and ret.vEgo < 0.001:
    #   events.add(EventName.manualRestart)
  
    # TODO: pcmEnable means use stock ACC
    # TODO: We should ignore buttons and use stock ACC state
    # TODO: create_common_events and create_button_enable_events appear to now handle this
    # TODO: Honda has the above extra code - this may explain scott's strange alerts!
    # Note: this update changes behavior - have steve / scott / uncle tone test / Bolt EUV test
    events = self.create_common_events(ret, extra_gears = [GearShifter.sport, GearShifter.low,
                                                           GearShifter.eco, GearShifter.manumatic], pcm_enable=self.CP.pcmCruise)

    if ret.vEgo < self.CP.minEnableSpeed:
      events.add(EventName.belowEngageSpeed)
    if ret.cruiseState.standstill:
      events.add(EventName.resumeRequired)
    if ret.vEgo < self.CP.minSteerSpeed:
      events.add(car.CarEvent.EventName.belowSteerSpeed)

    # handle button presses
    events.events.extend(create_button_enable_events(ret.buttonEvents, pcm_cruise=self.CP.pcmCruise))

    ret.events = events.to_msg()

    return ret

  def apply(self, c):
    ret = self.CC.update(c, self.CS)
    return ret
