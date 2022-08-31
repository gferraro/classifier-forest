"""
classifier-pipeline - this is a server side component that manipulates cptv
files and to create a classification model of animals present
Copyright (C) 2018, The Cacophony Project

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import attr
import logging
import numpy as np


@attr.s(eq=False)
class Rectangle:
    """Defines a rectangle by the topleft point and width / height."""

    x = attr.ib()
    y = attr.ib()
    width = attr.ib()
    height = attr.ib()

    @staticmethod
    def from_ltrb(left, top, right, bottom):
        """Construct a rectangle from left, top, right, bottom co-ords."""
        return Rectangle(left, top, width=right - left, height=bottom - top)

    def to_ltrb(self):
        """Return rectangle as left, top, right, bottom co-ords."""
        return [self.left, self.top, self.right, self.bottom]

    def to_ltwh(self):
        """Return rectangle as left, top, right, bottom co-ords."""
        return [self.left, self.top, self.width, self.height]

    def copy(self):
        return Rectangle(self.x, self.y, self.width, self.height)

    @property
    def mid(self):
        return (self.mid_x, self.mid_y)

    @property
    def mid_x(self):
        return self.x + self.width / 2

    def calculate_mass(self, filtered, threshold):
        """
        calculates mass on this frame for this region
        filtered is assumed to be cropped to the region
        """
        height, width = filtered.shape
        assert (
            width == self.width and height == self.height
        ), "calculating variance on incorrectly sized filtered"

        self.mass = tools.calculate_mass(filtered, threshold)

    @property
    def mid_y(self):
        return self.y + self.height / 2

    @property
    def left(self):
        return self.x

    @property
    def top(self):
        return self.y

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @left.setter
    def left(self, value):
        old_right = self.right
        self.x = value
        self.right = old_right

    @top.setter
    def top(self, value):
        old_bottom = self.bottom
        self.y = value
        self.bottom = old_bottom

    @right.setter
    def right(self, value):
        self.width = value - self.x

    @bottom.setter
    def bottom(self, value):
        self.height = value - self.y

    def overlap_area(self, other):
        """Compute the area overlap between this rectangle and another."""
        x_overlap = max(0, min(self.right, other.right) - max(self.left, other.left))
        y_overlap = max(0, min(self.bottom, other.bottom) - max(self.top, other.top))
        return x_overlap * y_overlap

    def crop(self, bounds):
        """Crops this rectangle so that it fits within given bounds"""
        self.left = min(bounds.right, max(self.left, bounds.left))
        self.top = min(bounds.bottom, max(self.top, bounds.top))
        self.right = max(bounds.left, min(self.right, bounds.right))
        self.bottom = max(bounds.top, min(self.bottom, bounds.bottom))

    def subimage(self, image):
        """Returns a subsection of the original image bounded by this rectangle
        :param image mumpy array of dims [height, width]
        """
        return image[
            self.top : self.top + self.height, self.left : self.left + self.width
        ]

    def enlarge(self, border, max=None):
        """Enlarges this by border amount in each dimension such that it fits
        within the boundaries of max"""
        self.left -= border
        self.right += border
        self.top -= border
        self.bottom += border
        if max:
            self.crop(max)

    @property
    def area(self):
        return int(self.width) * self.height

    def __repr__(self):
        return "(x{0},y{1},x2{2},y2{3})".format(
            self.left, self.top, self.right, self.bottom
        )

    def __str__(self):
        return "<(x{0},y{1})-h{2}xw{3}>".format(self.x, self.y, self.height, self.width)

    def meta_dictionary(self):
        # Return object as dictionary without is_along_border,was_cropped and id for saving to json
        region_info = attr.asdict(
            self,
            filter=lambda attr, value: attr.name
            not in ["is_along_border", "was_cropped", "id"],
        )
        region_info["pixel_variance"] = round(region_info["pixel_variance"], 2)
        return region_info


def eucl_distance(first, second):
    first_sq = first[0] - second[0]
    first_sq = first_sq * first_sq
    second_sq = first[1] - second[1]
    second_sq = second_sq * second_sq
    return first_sq + second_sq


def calculate_variance(filtered, prev_filtered):
    """Calculates variance of filtered frame with previous frame"""
    if prev_filtered is None:
        return
    delta_frame = np.abs(filtered - prev_filtered)
    return np.var(delta_frame)


@attr.s(eq=False)
class Region(Rectangle):
    """Region is a rectangle extended to support mass."""

    mass = attr.ib(default=0)
    # how much pixels in this region have changed since last frame
    frame_number = attr.ib(default=0)
    pixel_variance = attr.ib(default=0)
    id = attr.ib(default=0)

    # if this region was cropped or not
    was_cropped = attr.ib(default=False)
    blank = attr.ib(default=False)
    is_along_border = attr.ib(default=False)

    def rescale(self, factor):
        self.x = int(self.x * factor)
        self.y = int(self.y * factor)

        self.width = int(self.width * factor)
        self.height = int(self.height * factor)

    @staticmethod
    def from_ltwh(left, top, width, height):
        """Construct a rectangle from left, top, right, bottom co-ords."""
        return Region(left, top, width=width, height=height)

    def to_array(self):
        """Return rectangle as left, top, right, bottom co-ords."""
        return np.uint16(
            [
                self.left,
                self.top,
                self.right,
                self.bottom,
                self.frame_number,
                self.mass,
                1 if self.blank else 0,
            ]
        )

    @classmethod
    def region_from_array(cls, region_bounds):
        width = region_bounds[2] - region_bounds[0]
        height = region_bounds[3] - region_bounds[1]
        frame_number = None
        if len(region_bounds) > 4:
            frame_number = region_bounds[4]
        mass = 0
        if len(region_bounds) > 5:
            mass = region_bounds[5]
        blank = False
        if len(region_bounds) > 6:
            blank = region_bounds[6] == 1
        return cls(
            region_bounds[0],
            region_bounds[1],
            width,
            height,
            frame_number=np.uint16(frame_number) if frame_number is not None else None,
            mass=mass,
            blank=blank,
        )

    @classmethod
    def region_from_json(cls, region_json):
        frame = region_json.get("frame_number")
        if frame is None:
            frame = region_json.get("frameNumber")
        if frame is None:
            frame = region_json.get("order")
        return cls(
            region_json["x"],
            region_json["y"],
            region_json["width"],
            region_json["height"],
            frame_number=frame,
            mass=region_json.get("mass", 0),
            blank=region_json.get("blank", False),
            pixel_variance=region_json.get("pixel_variance", 0),
        )

    @staticmethod
    def from_ltrb(left, top, right, bottom):
        """Construct a rectangle from left, top, right, bottom co-ords."""
        return Region(left, top, width=right - left, height=bottom - top)

    def has_moved(self, region):
        """Determines if the region has shifted horizontally or veritcally
        Not just increased in width/height
        """
        return (self.x != region.x and self.right != region.right) or (
            self.y != region.y and self.bottom != region.bottom
        )

    def calculate_variance(self, filtered, prev_filtered):
        """
        calculates variance on this frame for this region
        filtered is assumed to be cropped to the region
        """
        height, width = filtered.shape
        assert (
            width == self.width and height == self.height
        ), "calculating variance on incorrectly sized filtered"
        self.pixel_variance = calculate_variance(filtered, prev_filtered)

    def set_is_along_border(self, bounds, edge=0):
        self.is_along_border = (
            self.was_cropped
            or self.x <= bounds.x + edge
            or self.y <= bounds.y + edge
            or self.right >= bounds.width - edge
            or self.bottom >= bounds.height - edge
        )

    def copy(self):
        return Region(
            self.x,
            self.y,
            self.width,
            self.height,
            self.mass,
            self.frame_number,
            self.pixel_variance,
            self.id,
            self.was_cropped,
            self.blank,
            self.is_along_border,
        )

    def average_distance(self, other):
        """Calculates the distance between 2 regions by using the distance between
        (top, left), mid points and (bottom,right) of each region
        """
        distances = []

        expected_x = int(other.x)
        expected_y = int(other.y)
        distance = eucl_distance((expected_x, expected_y), (self.x, self.y))
        distances.append(distance)

        expected_x = int(other.mid_x)
        expected_y = int(other.mid_y)
        distance = eucl_distance((expected_x, expected_y), (self.mid_x, self.mid_y))
        distances.append(distance)

        distance = eucl_distance(
            (
                other.right,
                other.bottom,
            ),
            (self.right, self.bottom),
        )
        # expected_x = int(other.right)
        # expected_y = int(other.bottom)
        # distance = tools.eucl_distance((expected_x, expected_y), (self.x, self.y))
        distances.append(distance)

        return distances

    def on_height_edge(self, crop_region):
        if self.top == crop_region.top or self.bottom == crop_region.bottom:
            return True
        return False

    def on_width_edge(self, crop_region):
        if self.left == crop_region.left or self.right == crop_region.right:
            return True
        return False
