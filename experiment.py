# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

# import os
# from csv import DictWriter
# from random import randrange
#
# # local imports
# from get_key_state import get_key_state  # type: ignore[import]
#
import klibs
from klibs import P
# from klibs.KLCommunication import message
# from klibs.KLGraphics import KLDraw as kld
# from klibs.KLGraphics import blit, fill, flip, clear
# from klibs.KLUserInterface import any_key, key_pressed, ui_request
# from klibs.KLUtilities import hide_mouse_cursor, line_segment_len, pump
# from klibs.KLBoundary import RectangleBoundary, BoundarySet
# from klibs.KLTime import CountDown
#
# from natnetclient_rough import NatNetClient  # type: ignore[import]
# from OptiTracker import OptiTracker  # type: ignore[import]


class sequential_pointing(klibs.Experiment):

    def setup(self):
        pass

    def block(self):
        pass

    def trial_prep(self):
        pass

    def trial(self):  # type: ignore[override]

        return {"block_num": P.block_number, "trial_num": P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass
