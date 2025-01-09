# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import os
from csv import DictWriter
from random import shuffle

import klibs
from klibs import P

from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld

from klibs.KLGraphics import fill, flip, blit, clear
from klibs.KLUserInterface import any_key, key_pressed, ui_request, mouse_pos

from klibs.KLUtilities import pump
from klibs.KLBoundary import CircleBoundary, BoundarySet

from klibs.KLTime import CountDown, Stopwatch
from klibs.KLExceptions import TrialException

# from natnetclient_rough import NatNetClient  # type: ignore[import]

LIKELY = "likely"
UNLIKELY = "unlikely"

GRAY = (128, 128, 128, 255)
WHITE = (255, 255, 255, 255)
ORANGE = (255, 165, 0, 255)


class sequential_pointing(klibs.Experiment):

    def setup(self):

        # self.nnc = NatNetClient()
        # self.nnc.marker_listener = self.marker_set_listener

        offset_y = P.screen_y * 0.2  # type: ignore[op_arithmetic]
        offset_x = P.screen_x * 0.25  # type: ignore[op_arithmetic]

        placeholder_size = P.ppi

        self.placeholder = kld.Circle(diameter=placeholder_size, fill=WHITE)
        self.target = kld.Circle(diameter=placeholder_size, fill=ORANGE)

        self.locs = {
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
                for loc in ["mid", "left", "right"]
            ]
        )

        # create participant directory for mocap data
        if not os.path.exists("OptiData"):
            os.mkdir("OptiData")

        os.mkdir(f"OptiData/{P.p_id}")
        os.mkdir(f"OptiData/{P.p_id}/testing")

        # set up condition factors
        self.condition_sequence = ["delayed", "immediate", "delayed"]
        self.likely_location = ["left", "right"]
        shuffle(self.likely_location)

        # expand task sequence to include practice blocks
        if P.run_practice_blocks:
            os.mkdir(f"OptiData/{P.p_id}/practice")

            # expand factor sequences for practice blocks
            self.condition_sequence = [
                cond for _ in range(2) for cond in self.condition_sequence
            ]
            self.likely_location = [
                loc for _ in range(2) for loc in self.likely_location
            ]

            # insert practice blocks
            self.insert_practice_block([1, 3, 5], trial_counts=P.trials_per_practice_block)  # type: ignore[arg-type]

    def block(self):
        # extract block factors
        self.block_condition = self.condition_sequence.pop(0)

        # swap likely location for second half of experiment
        if P.block_number > P.blocks_per_experiment // 2:
            self.likely_location = self.likely_location[::-1]

        # map likelihoods to locations
        self.block_likelihood = {
            LIKELY: self.likely_location[0],
            UNLIKELY: self.likely_location[1],
        }

        # init block specific data dirs for mocap recordings
        self.opti_dir = f"OptiData/{P.p_id}"
        self.opti_dir += "/practice" if P.practicing else "/testing"
        self.opti_dir += f"/block_{P.block_number}_{self.block_condition}_targets_{self.block_likelihood[LIKELY]}_bias"

        if os.path.exists(self.opti_dir):
            raise RuntimeError(f"Data directory already exists at {self.opti_dir}")
        else:
            os.mkdir(self.opti_dir)

        # TODO: add task instructions
        instrux = "tbd\n\nPress any key to begin."

        fill()
        message(text=instrux, location=P.screen_c, blit_txt=True)
        flip()

        any_key()

    def trial_prep(self):
        # establish target location
        self.target_loc = self.locs[self.block_likelihood[self.target_location]]  # type: ignore[attr-defined]

        # generate trial file location
        self.opti_dir = (
            self.opti_dir + f"/{P.trial_number}_target_at_" + "left"
            if self.block_likelihood[self.target_location] == "left"  # type: ignore[attr-defined]
            else "right"
        )

        self.present_stimuli(pre_trial=True)

        # participant readiness signalled by keypress
        while True:
            q = pump(True)
            # on keypress, start mocap recording (w/ some lead time)
            if key_pressed(key="space", queue=q):
                # self.nnc.startup()

                nnc_lead = CountDown(0.3)
                while nnc_lead.counting():
                    q = pump(True)
                    ui_request(queue=q)

                break

        mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[op_arithmetic]
        self.present_stimuli(target_visible=self.block_condition == "immediate")

    def trial(self):  # type: ignore[override]
        time_to_center = None
        time_to_selection = None
        touched_center = False
        touched_placeholder = False
        placeholder_touched = None

        trial_timer = Stopwatch()


        while not touched_center:
            q = pump(True)
            _ = ui_request(queue=q)

            curr_pos = mouse_pos()

            which_bound = self.boundaries.which_boundary(curr_pos)

            if which_bound is not None:

                if which_bound != "mid":
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

                else:
                    time_to_center = trial_timer.elapsed()
                    touched_center = True

        if self.block_condition == "delayed":
            self.present_stimuli(target_visible=True)

        while not touched_placeholder:
            q = pump(True)
            _ = ui_request(queue=q)

            curr_pos = mouse_pos()

            which_bound = self.boundaries.which_boundary(curr_pos)

            if which_bound is not None and which_bound != "mid":
                time_to_selection = trial_timer.elapsed()
                placeholder_touched = which_bound
                touched_placeholder = True

        # self.nnc.shutdown()
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
                    registration=5
                )
            else:
                colour = GRAY if pre_trial else WHITE
                blit(
                    kld.Circle(diameter=P.ppi, fill=colour).render(),
                    location=self.locs[loc],
                    registration=5
                )

        flip()

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
