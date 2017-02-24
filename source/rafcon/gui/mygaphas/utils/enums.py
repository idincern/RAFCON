# Copyright

from enum import Enum

Direction = Enum('DIRECTION', 'UP DOWN LEFT RIGHT')


class SnappedSide(Enum):
    LEFT = 1
    TOP = 2
    RIGHT = 3
    BOTTOM = 4

    def next(self):
        val = self.value + 1
        if val == 5:
            val = 1
        return SnappedSide(val)

    def prev(self):
        val = self.value - 1
        if val == 0:
            val = 4
        return SnappedSide(val)

    def opposite(self):
        val = self.value
        if val == 1:
            return SnappedSide(3)
        elif val == 2:
            return SnappedSide(4)
        elif val == 3:
            return SnappedSide(1)
        elif val == 4:
            return SnappedSide(2)
