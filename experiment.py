# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

from random import shuffle, choice
from rich.console import Console
import os
from csv import DictWriter

from math import floor

import klibs
from klibs import P

from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld

from klibs.KLGraphics import fill, flip, blit, clear
from klibs.KLUserInterface import (
    any_key,
    ui_request,
    mouse_pos,
    mouse_clicked,
)

from klibs.KLUtilities import pump
from klibs.KLBoundary import CircleBoundary, BoundarySet

from klibs.KLTime import CountDown
from klibs.KLExceptions import TrialException

from natnetclient_rough import NatNetClient  # type: ignore[import]

LIKELY = "likely"
UNLIKELY = "unlikely"
DELAYED = "delayed"
IMMEDIATE = "immediate"
LEFT = "left"
RIGHT = "right"
CENTER = "center"
START = "start"


GRAY = (128, 128, 128, 255)
WHITE = (255, 255, 255, 255)
ORANGE = (255, 165, 0, 255)

# Position offsets for circles (in inches)
CENTER_OFFSET = 10
TARGET_OFFSET_Y = 20
TARGET_OFFSET_X = 5


class sequential_pointing(klibs.Experiment):

    def setup(self):
        self.console = Console()

        self.nnc = NatNetClient()
        self.nnc.markers_listener = self.marker_set_listener

        placeholder_size = P.ppi

        y_start = P.screen_y  # type: ignore[op_arithmetic]
        y_middle = P.screen_y - (P.ppi * CENTER_OFFSET)  # type: ignore[op_arithmetic]
        y_targets = P.screen_y - (P.ppi * TARGET_OFFSET_Y)  # type: ignore[op_arithmetic]
        x_left = P.screen_c[0] - (P.ppi * TARGET_OFFSET_X)  # type: ignore[op_arithmetic]
        x_right = P.screen_c[0] + (P.ppi * TARGET_OFFSET_X)  # type: ignore[op_arithmetic]

        self.placeholder = kld.Circle(diameter=placeholder_size, fill=WHITE)
        self.target = kld.Circle(diameter=placeholder_size, fill=ORANGE)

        self.locs = {
            START: (P.screen_c[0], y_start),  # type: ignore[op_arithmetic]
            CENTER: (P.screen_c[0], y_middle),  # type: ignore[op_arithmetic]
            LEFT: (x_left, y_targets),
            RIGHT: (x_right, y_targets),
        }

        # boundaries for click detection
        self.bs = BoundarySet(
            [
                CircleBoundary(
                    label=loc, center=self.locs[loc], radius=placeholder_size // 2
                )
                for loc in [START, CENTER, LEFT, RIGHT]
            ]
        )

        # create participant directory for mocap data
        if not os.path.exists("OptiData"):
            os.mkdir("OptiData")

        os.mkdir(f"OptiData/{P.p_id}")
        os.mkdir(f"OptiData/{P.p_id}/testing")

        # set up condition factors
        # NOTE: first "delayed" is to serve as the practice block
        self.condition_sequence = [
            DELAYED,
            DELAYED,
            IMMEDIATE,
            IMMEDIATE,
            DELAYED,
        ]
        self.likely_location = [LEFT, RIGHT]

        # randomize initial location bias across participants
        shuffle(self.likely_location)

        # expand task sequence to include practice blocks
        if P.run_practice_blocks:
            os.mkdir(f"OptiData/{P.p_id}/practice")

            # insert practice blocks
            self.insert_practice_block(1, trial_counts=P.trials_per_practice_block)  # type: ignore[arg-type]

        # Otherwise, drop practice block
        else:
            _ = self.condition_sequence.pop(0)

        if P.development_mode:
            print("-------------------------")
            print("setup()")
            print("-------------------------")
            self.console.log(log_locals=True)

    def block(self):
        # get block condition
        self.block_condition = self.condition_sequence.pop(0)

        # swap likelihoods for second "delayed" block
        if P.block_number == 4:
            self.likely_location = self.likely_location[::-1]

        # map likelihoods to locations
        self.block_likelihood = {
            LIKELY: self.likely_location[0],
            UNLIKELY: self.likely_location[1],
        }

        # init block specific data dirs for mocap recordings
        self.opti_dir = f"OptiData/{P.p_id}"
        self.opti_dir += "/practice" if P.practicing else "/testing"

        self.opti_dir += f"/{P.block_number}_{self.block_condition}_{self.block_likelihood[LIKELY]}_bias"

        if os.path.exists(self.opti_dir):
            raise RuntimeError(f"Data directory already exists at {self.opti_dir}")
        else:
            os.mkdir(self.opti_dir)

        self.present_instructions()

        if P.development_mode:
            print("-------------------------")
            print("block()")
            print("-------------------------")
            self.console.log(log_locals=True)

    def trial_prep(self):

        # klibs lacks a direct method of altering independent variables at the block level,
        # so need to manually select target location to (mostly) fix the odds at 1:1.
        if self.block_condition == IMMEDIATE:
            self.target_location = choice([LIKELY, UNLIKELY])

        # establish target location
        self.target_loc = self.locs[self.block_likelihood[self.target_location]]  # type: ignore[attr-defined]

        # generate trial file location
        self.opti_trial_fname = f"/trial_{P.trial_number}_{self.block_likelihood[self.target_location]}_target"

        self.present_stimuli(pre_trial=True)

        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y - P.ppi))  # type: ignore[op_arithmetic]

        # wait for participant to touch start position before proceeding
        while True:
            q = pump(True)
            _ = ui_request(queue=q)

            # check for start position touch
            if mouse_clicked(within=self.bs.boundaries[START], queue=q):
                break

        # spin up mocap listener
        self.nnc.startup()

        # provide opti a 10 frame head start
        nnc_lead = CountDown((1 / 120) * 10)
        while nnc_lead.counting():
            q = pump(True)
            ui_request(queue=q)

        # For "immediate" blocks, present target at trial start
        self.present_stimuli(target_visible=self.block_condition == IMMEDIATE)

        if P.development_mode:
            print("-------------------------")
            print("trial_prep()")
            print("-------------------------")
            self.console.log(log_locals=True)

    def trial(self):  # type: ignore[override]
        time_to_center = None
        time_to_selection = None
        touched_center = False
        touched_placeholder = False
        placeholder_touched = None

        # particpants must touch center before anything else
        while not touched_center:
            q = pump(True)
            _ = ui_request(queue=q)

            pos = mouse_pos()
            is_within = self.bs.which_boundary(p=pos, ignore=[START])

            if is_within == CENTER:
                time_to_center = self.evm.trial_time_ms
                touched_center = True

            elif is_within is None:
                self.console.log(pos, is_within, log_locals=True)
                self.admonish(
                    msg="Unexpected error; get Brett",
                    die=True,
                )

            else:
                self.admonish(msg="Must touch center circle first!", err="not center")

        # following center touch, present target if in "delayed" condition
        if self.block_condition == DELAYED:
            self.present_stimuli(target_visible=True)

        # wait for contact with either target placeholder
        while not touched_placeholder:
            q = pump(True)
            _ = ui_request(queue=q)

            pos = mouse_pos()
            is_within = self.bs.which_boundary(p=pos, ignore=[START])

            if is_within in [CENTER, None]:
                self.admonish(
                    msg="Must touch either the left or right circle after touching center",
                    err="not target",
                )

            elif is_within in [LEFT, RIGHT]:
                time_to_selection = self.evm.time_elapsed
                placeholder_touched = is_within
                touched_placeholder = True

            else:
                self.console.log(pos, is_within, log_locals=True)
                self.admonish(msg="Unexpected error; get Brett", die=True)

        trial_out = {
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "practicing": P.practicing,
            "block_condition": self.block_condition,
            "location_bias": self.block_likelihood[LIKELY],
            "target_location": self.block_likelihood[self.target_location],  # type: ignore[attr-defined]
            "item_touched": placeholder_touched,
            "time_to_center": time_to_center,
            "time_to_selection": time_to_selection,
            "correct": placeholder_touched == self.block_likelihood[self.target_location],  # type: ignore[attr-defined]
        }

        if P.development_mode:
            print("-------------------------")
            print("trial(): end")
            print("-------------------------")
            self.console.log(log_locals=True)

        return trial_out

    def trial_clean_up(self):
        self.nnc.shutdown()
        clear()

    def clean_up(self):
        self.nnc.shutdown()

    def present_stimuli(self, pre_trial: bool = False, target_visible: bool = False):
        fill()

        for loc in self.locs:
            if target_visible and loc == self.block_likelihood[self.target_location]:  # type: ignore[attr-defined]
                blit(
                    kld.Circle(diameter=P.ppi, fill=ORANGE).render(),
                    location=self.locs[loc],
                    registration=5,
                )
            else:
                colour = GRAY if pre_trial else WHITE
                blit(
                    kld.Circle(diameter=P.ppi, fill=colour).render(),
                    location=self.locs[loc],
                    registration=5,
                )

        flip()

        if P.development_mode:
            print("-------------------------")
            print("present_stimuli()")
            print("-------------------------")
            self.console.log(log_locals=True)

    def present_instructions(self):
        delayed_txt = (
            "To begin a trial, place your right index finger at the starting circle (bottom center of the monitor)."
            "\n\n"
            "Once you do, all circles will turn white. When that happens, touch the MIDDLE circle with your finger as quickly and accurately as possible."
            "\n\n"
            "Once you've touched the middle circle, one of the two furthest circles will turn orange. Your task is then to touch the orange circle as quickly and accurately as possible."
            "\n\n"
            "Once the trial is complete, place your finger back at the starting circle to begin the next trial."
        )

        immediate_txt = (
            "To begin a trial, place your right index finger at the starting circle (bottom center of the monitor)."
            "\n\n"
            "Once you do, all circles will turn white, except for one of the two furthest circles, which will turn orange."
            "\n\n"
            "Once this happens, reach to touch the middle circle FIRST, as quickly and accurately as possible. THEN, touch the orange circle as quickly and accurately as possible."
            "\n\n"
            "Once the trial is complete, place your finger back at the starting circle to begin the next trial."
        )

        instrux = delayed_txt if self.block_condition == DELAYED else immediate_txt

        if P.practicing:
            instrux += (
                "\n\n"
                "This PRACTICE block will consist of 5 trials."
                "\n\n"
                "(press any key to begin the block)"
            )

        else:
            instrux += (
                "\n\n"
                "This block will consist of 50 trials."
                "\n\n"
                "(press any key to begin the block)"
            )

        fill()
        message(
            text=instrux,
            location=P.screen_c,
            wrap_width=floor(P.screen_x * 0.8),  # type: ignore[operator]
            blit_txt=True,
        )
        flip()

        any_key()

    def admonish(self, msg: str = "", err: str = "", die: bool = False) -> None:

        if msg:
            fill()
            message(text=msg, location=P.screen_c, registration=5, blit_txt=True)
            flip()

            counter = CountDown(1)
            while counter.counting():
                q = pump(True)
                _ = ui_request(queue=q)

        if die:
            quit()

        else:
            raise TrialException(err)

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """
        pass

        if marker_set.get("label") == "hand":
            # Append data to trial-specific CSV file
            fname = self.opti_dir + self.opti_trial_fname

            # Timestamp marker data with relative trial time
            header = list(marker_set["markers"][0].keys())

            # if file doesn't exist, create it and write header
            if not os.path.exists(fname):
                with open(fname, "w", newline="") as file:
                    writer = DictWriter(file, fieldnames=header)
                    writer.writeheader()

            # append marker data to file
            with open(fname, "a", newline="") as file:
                writer = DictWriter(file, fieldnames=header)
                for marker in marker_set.get("markers", None):
                    if marker is not None:
                        writer.writerow(marker)
