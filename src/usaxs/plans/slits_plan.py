"""
Plans for slits alignment and control in USAXS experiments.
"""


def plan_slit_ok():
    """Create a plan to check and adjust slit positions.

    This function returns a class with methods to check and adjust
    slit positions, ensuring they are within specified tolerances.

    Returns:
        class: A class containing methods for slit position management
    """

    def set_size(
        self, *args: Any, h: Optional[float] = None, v: Optional[float] = None
    ) -> Generator[Any, None, None]:
        """Move the slits to the specified size.

        Args:
            h: Horizontal size to set
            v: Vertical size to set

        Yields:
            Generator: Control flow for motor movement

        Raises:
            ValueError: If horizontal size is not specified
        """
        if h is None:
            raise ValueError("must define horizontal size")
        if v is None:
            raise ValueError("must define vertical size")
        # move_motors(self.h_size, h, self.v_size, v)
        yield from bps.mv(
            self.h_size,
            h,
            self.v_size,
            v,
        )

    @property
    def h_gap_ok(self) -> bool:
        """
        Check if the horizontal gap is within tolerance.

        Returns:
            bool: True if the horizontal gap is within tolerance, False otherwise.
        """
        gap = self.outb.position - self.inb.position
        return abs(gap - terms.SAXS.guard_h_size.get()) <= self.gap_tolerance

    @property
    def v_h_gap_ok(self) -> bool:
        """
        Check if the vertical gap is within tolerance.

        Returns:
            bool: True if the vertical gap is within tolerance, False otherwise.
        """
        gap = self.top.position - self.bot.position
        return abs(gap - terms.SAXS.guard_v_size.get()) <= self.gap_tolerance

    @property
    def gap_ok(self) -> bool:
        """
        Check if both horizontal and vertical gaps are within tolerance.

        Returns:
            bool: True if both gaps are within tolerance, False otherwise.
        """
        return self.h_gap_ok and self.v_h_gap_ok

    def process_motor_records(self) -> Generator[Any, None, None]:
        """
        Process motor records to update their status.

        Yields:
            Generator: A generator that yields control flow back to the caller.
        """
        yield from bps.mv(self.top.process_record, 1)
        yield from bps.mv(self.outb.process_record, 1)
        yield from bps.sleep(0.05)
        yield from bps.mv(self.bot.process_record, 1)
        yield from bps.mv(self.inb.process_record, 1)
        yield from bps.sleep(0.05)
