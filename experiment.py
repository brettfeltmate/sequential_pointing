# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import os
from csv import DictWriter
from random import shuffle, choice

import klibs
from klibs import P

from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld

from klibs.KLGraphics import fill, flip, blit, clear
from klibs.KLUserInterface import any_key, ui_request, mouse_pos

from klibs.KLUtilities import pump
from klibs.KLBoundary import CircleBoundary, BoundarySet

from klibs.KLTime import CountDown, Stopwatch
from klibs.KLExceptions import TrialException

from natnetclient_rough import NatNetClient  # type: ignore[import]

LIKELY = "likely"
UNLIKELY = "unlikely"

GRAY = (128, 128, 128, 255)
WHITE = (255, 255, 255, 255)
ORANGE = (255, 165, 0, 255)


class sequential_pointing(klibs.Experiment):

    def setup(self):

        self.nnc = NatNetClient()
        self.nnc.marker_listener = self.marker_set_listener

        offset_y = P.screen_y * 0.2  # type: ignore[op_arithmetic]
        offset_x = P.screen_x * 0.25  # type: ignore[op_arithmetic]

        placeholder_size = P.ppi

        self.placeholder = kld.Circle(diameter=placeholder_size, fill=WHITE)
        self.target = kld.Circle(diameter=placeholder_size, fill=ORANGE)

        self.locs = {
            "start": (P.screen_x // 2, P.screen_y),  # type: ignore[op_arithmetic]
            "mid": (P.screen_x // 2, P.screen_y - offset_y),  # type: ignore[op_arithmetic]
            "left": (offset_x, offset_y),
            "right": (P.screen_x - offset_x, offset_y),
        }

        # boundaries for click detection
        self.boundaries = BoundarySet(
            [
                CircleBoundary(
                    label=loc, center=self.locs[loc], radius=placeholder_size // 2
                )
                for loc in ["start", "mid", "left", "right"]
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
            "delayed",
            "delayed",
            "immediate",
            "immediate",
            "delayed",
        ]
        self.likely_location = ["left", "right"]

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

        self.opti_dir += f"/{self.block_condition}_{self.block_likelihood[LIKELY]}_bias"

        if os.path.exists(self.opti_dir):
            raise RuntimeError(f"Data directory already exists at {self.opti_dir}")
        else:
            os.mkdir(self.opti_dir)

        self.present_instructions()

    def trial_prep(self):

        # klibs lacks a direct method of altering independent variables at the block level,
        # so need to manually select target location to (mostly) fix the odds at 1:1.
        if self.block_condition == "immediate":
            self.target_location = choice([LIKELY, UNLIKELY])

        # establish target location
        self.target_loc = self.locs[self.block_likelihood[self.target_location]]  # type: ignore[attr-defined]

        # generate trial file location
        self.opti_dir = (
            self.opti_dir + f"/{P.trial_number}_target_at_" + "left"
            if self.block_likelihood[self.target_location] == "left"  # type: ignore[attr-defined]
            else "right"
        )

        self.present_stimuli(pre_trial=True)

        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[op_arithmetic]

        at_start_position = False

        # wait for participant to touch start position before proceeding
        while not at_start_position:
            q = pump(True)
            _ = ui_request(queue=q)

            # check for start position touch
            if self.boundaries.which_boundary(mouse_pos()) == "start":
                at_start_position = True

        # spin up mocap listener
        self.nnc.startup()

        # provide opti a 10 frame head start
        nnc_lead = CountDown((1 / 120) * 10)
        while nnc_lead.counting():
            q = pump(True)
            ui_request(queue=q)

        # For "immediate" blocks, present target at trial start
        self.present_stimuli(target_visible=self.block_condition == "immediate")

    def trial(self):  # type: ignore[override]
        time_to_center = None
        time_to_selection = None
        touched_center = False
        touched_placeholder = False
        placeholder_touched = None

        trial_timer = Stopwatch()

        # particpants must touch center before anything else
        while not touched_center:
            q = pump(True)
            _ = ui_request(queue=q)

            # continuously check for boundary touches
            which_bound = self.boundaries.which_boundary(p=mouse_pos())
            if which_bound is not None:

                # admonish participant for skipping center

                if which_bound == "left" or which_bound == "right":
                    clear()

                    fill()
                    message(
                        "Must touch center before touching target",
                        location=P.screen_c,
                        blit_txt=True,
                    )
                    flip()

                    abort_delay = CountDown(1)
                    while abort_delay.counting():
                        q = pump(True)
                        _ = ui_request(queue=q)

                    raise TrialException(
                        "Participant touched placeholder before center"
                    )

                elif which_bound == "mid":
                    # record time to center touch
                    time_to_center = trial_timer.elapsed()
                    touched_center = True

                # silently ignore start position touches/hovering
                else:
                    pass

        # following center touch, present target if in "delayed" condition
        if self.block_condition == "delayed":
            self.present_stimuli(target_visible=True)

        # wait for contact with either target placeholder
        while not touched_placeholder:
            q = pump(True)
            _ = ui_request(queue=q)

            which_bound = self.boundaries.which_boundary(p=mouse_pos())

            if which_bound == "left" or which_bound == "right":
                time_to_selection = trial_timer.elapsed()
                placeholder_touched = which_bound
                touched_placeholder = True

        self.nnc.shutdown()
        clear()

        return {
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

    def trial_clean_up(self):
        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[op_arithmetic]

    def clean_up(self):
        pass

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

    def present_instructions(self):
        delayed = (
            "To begin a trial, place your right index finger at the starting circle (bottom center of the monitor)."
            "\n\n"
            "Once you do, all circles will turn white. When that happens, touch the MIDDLE circle with your finger"
            "\n"
            "as quickly and accurately as possible."
            "\n\n"
            "Once you've touched the middle circle, one of the two furthest circles will turn orange."
            "\n"
            "Your task is then to touch the orange circle as quickly and accurately as possible."
            "\n\n"
            "Once the trial is complete, place your finger back at the starting circle to begin the next trial."
        )

        immediate = (
            "To begin a trial, place your right index finger at the starting circle (bottom center of the monitor)."
            "\n\n"
            "Once you do, all circles will turn white, except for one of the two furthest circles, which will turn orange."
            "\n\n"
            "Once this happens, reach to touch the middle circle FIRST, as quickly and accurately as possible."
            "\n"
            "THEN, touch the orange circle as quickly and accurately as possible."
            "\n\n"
            "Once the trial is complete, place your finger back at the starting circle to begin the next trial."
        )

        instrux = delayed if self.block_condition == "delayed" else immediate

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
        message(text=instrux, location=P.screen_c, blit_txt=True)
        flip()

        any_key()

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """

        if marker_set.get("label") == "hand":
            # Append data to trial-specific CSV file
            fname = self.opti_dir

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
