class DataProcessor:
    """Dummy class to process traces and compute integrated ROI."""
    def __init__(self, roi=None):
        self.roi = roi or (20, 80) # roi can be a tuple (start_index, end_index)

    def process(self, trace):
        """
        Process trace and compute ROI integration.
        Args:
            trace (tuple): (time_array, signal_array)
        Returns:
            float: integrated value over the ROI
        """
        t, signal = trace
        # Ensure ROI indices are within the bounds of the signal array
        start_idx = min(self.roi[0], len(signal) -1)
        end_idx = min(self.roi[1], len(signal))
        if start_idx >= end_idx: # handle cases where ROI is invalid for current signal length
            return 0.0
        integrated_value = signal[start_idx:end_idx].sum()
        return integrated_value