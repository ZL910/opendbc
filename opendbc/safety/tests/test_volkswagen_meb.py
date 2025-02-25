#!/usr/bin/env python3
import unittest
import numpy as np
from opendbc.car.structs import CarParams
from opendbc.safety.tests.libsafety import libsafety_py
import opendbc.safety.tests.common as common
from opendbc.safety.tests.common import CANPackerPanda
from opendbc.car.volkswagen.values import VolkswagenSafetyFlags

MSG_LH_EPS_03 = 0x9F    # RX from EPS, for driver steering torque
MSG_ESC_51 = 0xFC       # RX, for wheel speeds
MSG_Motor_54 = 0x14C    # RX, for accel pedal
MSG_ESC_50 = 0x102      # RX, for yaw rate
MSG_VMM_02 = 0x139      # RX, for ESP hold management
MSG_EA_01 = 0x1A4       # TX, for EA mitigation
MSG_EA_02 = 0x1F0       # TX, for EA mitigation
MSG_EML_06 = 0x20A      # RX, for yaw rate
MSG_HCA_03 = 0x303      # TX by OP, Heading Control Assist steering torque
MSG_QFK_01 = 0x13D      # RX, for steering angle
MSG_MEB_ACC_01 = 0x300  # RX from ECU, for ACC status
MSG_ACC_18 = 0x14D      # RX from ECU, for ACC status
MSG_GRA_ACC_01 = 0x12B  # TX by OP, ACC control buttons for cancel/resume
MSG_MOTOR_14 = 0x3BE    # RX from ECU, for brake switch status
MSG_LDW_02 = 0x397      # TX by OP, Lane line recognition and text alerts
MSG_Motor_51 = 0x10B    # RX for TSK state
MSG_TA_01 = 0x26B       # TX for Travel Assist status


class TestVolkswagenMebSafety(common.PandaCarSafetyTest):
  STANDSTILL_THRESHOLD = 0
  RELAY_MALFUNCTION_ADDRS = {0: (MSG_HCA_03,)}

  DRIVER_TORQUE_ALLOWANCE = 80
  DRIVER_TORQUE_FACTOR = 3

  @classmethod
  def setUpClass(cls):
    if cls.__name__ == "TestVolkswagenMebSafety":
      cls.packer = None
      cls.safety = None
      raise unittest.SkipTest

  def _speed_msg(self, speed):
    values = {"%s_Radgeschw" % s: speed for s in ["HL", "HR", "VL", "VR"]}
    return self.packer.make_can_msg_panda("ESC_51", 0, values)

  # TODO: does MEB have a usable redundant brake signal?
  # Driver brake pressure over threshold
  # def _esp_05_msg(self, brake):
  #   values = {"ESP_Fahrer_bremst": brake}
  #   return self.packer.make_can_msg_panda("ESP_05", 0, values)

  # TODO: consolidate with MQB
  # Brake pedal switch
  def _motor_14_msg(self, brake):
    values = {"MO_Fahrer_bremst": brake}
    return self.packer.make_can_msg_panda("Motor_14", 0, values)

  def _user_brake_msg(self, brake):
    return self._motor_14_msg(brake)

  # Driver throttle input
  def _user_gas_msg(self, gas):
    values = {"Accelerator_Pressure": gas}
    return self.packer.make_can_msg_panda("Motor_54", 0, values)

  # TODO: simplify to _pcm_status_msg, consolidate with MQB
  # ACC engagement status
  def _tsk_status_msg(self, enable, main_switch=True):
    if main_switch:
      tsk_status = 3 if enable else 2
    else:
      tsk_status = 0
    values = {"TSK_Status": tsk_status}
    return self.packer.make_can_msg_panda("Motor_51", 0, values)

  def _pcm_status_msg(self, enable):
    return self._tsk_status_msg(enable)

  # TODO: consolidate with MQB
  # Driver steering input torque
  def _torque_driver_msg(self, torque):
    values = {"EPS_Lenkmoment": abs(torque), "EPS_VZ_Lenkmoment": torque < 0}
    return self.packer.make_can_msg_panda("LH_EPS_03", 0, values)

  # FIXME: replace with curvature control
  # openpilot steering output torque
  # def _torque_cmd_msg(self, torque, steer_req=1):
  #   pass

  # TODO: consolidate with MQB
  # Cruise control buttons
  def _gra_acc_01_msg(self, cancel=0, resume=0, _set=0, bus=2):
    values = {"GRA_Abbrechen": cancel, "GRA_Tip_Setzen": _set, "GRA_Tip_Wiederaufnahme": resume}
    return self.packer.make_can_msg_panda("GRA_ACC_01", bus, values)

  # Acceleration request to drivetrain coordinator
  def _acc_18_msg(self, accel):
    values = {"ACC_Sollbeschleunigung_02": accel}
    return self.packer.make_can_msg_panda("ACC_18", 0, values)

  # TODO: consolidate with MQB
  def test_torque_measurements(self):
    # TODO: make this test work with all cars
    self._rx(self._torque_driver_msg(50))
    self._rx(self._torque_driver_msg(-50))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))
    self._rx(self._torque_driver_msg(0))

    self.assertEqual(-50, self.safety.get_torque_driver_min())
    self.assertEqual(50, self.safety.get_torque_driver_max())

    self._rx(self._torque_driver_msg(0))
    self.assertEqual(0, self.safety.get_torque_driver_max())
    self.assertEqual(-50, self.safety.get_torque_driver_min())

    self._rx(self._torque_driver_msg(0))
    self.assertEqual(0, self.safety.get_torque_driver_max())
    self.assertEqual(0, self.safety.get_torque_driver_min())


class TestVolkswagenMebStockSafety(TestVolkswagenMebSafety):
  TX_MSGS = [[MSG_HCA_03, 0], [MSG_LDW_02, 0], [MSG_GRA_ACC_01, 0], [MSG_EA_01, 0], [MSG_EA_02, 0], [MSG_GRA_ACC_01, 2]]
  FWD_BLACKLISTED_ADDRS = {2: [MSG_HCA_03, MSG_LDW_02, MSG_EA_01, MSG_EA_02]}
  FWD_BUS_LOOKUP = {0: 2, 2: 0}

  def setUp(self):
    self.packer = CANPackerPanda("vw_meb")
    self.safety = libsafety_py.libsafety
    self.safety.set_safety_hooks(CarParams.SafetyModel.volkswagenMeb, 0)
    self.safety.init_tests()

  def test_spam_cancel_safety_check(self):
    self.safety.set_controls_allowed(0)
    self.assertTrue(self._tx(self._gra_acc_01_msg(cancel=1)))
    self.assertFalse(self._tx(self._gra_acc_01_msg(resume=1)))
    self.assertFalse(self._tx(self._gra_acc_01_msg(_set=1)))
    # do not block resume if we are engaged already
    self.safety.set_controls_allowed(1)
    self.assertTrue(self._tx(self._gra_acc_01_msg(resume=1)))


if __name__ == "__main__":
  unittest.main()
