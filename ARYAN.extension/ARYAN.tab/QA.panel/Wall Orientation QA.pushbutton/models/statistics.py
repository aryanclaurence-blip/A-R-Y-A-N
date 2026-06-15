# -*- coding: utf-8 -*-
"""QA statistics model for Wall Orientation QA."""


class QAStatistics(object):
    """Aggregated counts for the current analysis session."""

    def __init__(self):
        self.ReferenceCount = 0
        self.ParallelCount = 0
        self.PerpendicularCount = 0
        self.InvalidCount = 0
        self.TotalWallCount = 0

    def reset_analysis_counts(self):
        self.ParallelCount = 0
        self.PerpendicularCount = 0
        self.InvalidCount = 0
        self.TotalWallCount = 0

    def update_from_results(self, results):
        self.reset_analysis_counts()
        self.TotalWallCount = len(results)
        for result in results.values():
            if result.Status == "Parallel":
                self.ParallelCount += 1
            elif result.Status == "Perpendicular":
                self.PerpendicularCount += 1
            else:
                self.InvalidCount += 1
