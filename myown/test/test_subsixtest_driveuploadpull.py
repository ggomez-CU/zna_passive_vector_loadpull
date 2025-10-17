import unittest
# import src.focustuner
from focustuner import *
from focustuner.Tuner import * 

class test_connected_successfully(unittest.TestCase):

    def setUp(self):
        self.loadtuner = Tuner()

    def test_1_successfulConnection(self):
        # Connect to load tuner -> return self.connected = True
        self.assertTrue(self.loadtuner.connect())

        # Checks that the load tuner is able to get ready -> return status_code = 0
        self.assertEqual(self.loadtuner.waitForReady(),0)

        #Initial position of all axis' is 0
        self.assertEqual(self.loadtuner.pos(),[0,0,0])

        #Move, status, pos
        self.assertEqual(self.loadtuner.move('x',100),[100,0,0])
        # self.assertEqual(self.loadtuner.status(),1)
        self.loadtuner.waitForReady()
        self.assertEqual(self.loadtuner.status(),0)
        self.assertEqual(self.loadtuner.pos(),[100,0,0])

        # Close Connection -> return self.connected = False
        self.assertFalse(self.loadtuner.close())

        # # Close already closed Connection -> return self.connected = None
        self.assertIsNone(self.loadtuner.close())

class test_connected_unsuccessfully(unittest.TestCase):

    def setUp(self):
        self.loadtuner = Tuner(address='0.0.0.0')

    def test_unsuccessfulConnection(self):
        self.assertFalse(self.loadtuner.connect())
        self.assertIsNone(self.loadtuner.close())

if __name__ == '__main__':
    unittest.main()
