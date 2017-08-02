class Beat(object):
    def __init__(self, bpm, sample_rate, pixel_per_sample):
        self.bpm = bpm
        self.sample_rate = sample_rate
        self.pixel_per_sample = pixel_per_sample
        self.div_per_beat = 4
        self.calculate()

    def set_bpm(self, bpm):
        self.bpm = bpm
        self.calculate()

    def set_sample_rate(self, sample_rate):
        self.sample_rate = sample_rate
        self.calculate()

    def set_pixel_per_sample(self, pixel_per_sample):
        self.pixel_per_sample = pixel_per_sample
        self.calculate()

    def calculate(self):
        self.div_sample_unit = ((60./(self.bpm*self.div_per_beat))*self.sample_rate)
        self.beat_pixel_unit = self.div_sample_unit*self.pixel_per_sample
        self.div_pixel_unit = self.beat_pixel_unit*1./self.div_per_beat

    def pixel2sample(self, pixel):
        sample = pixel*1./self.pixel_per_sample
        sample = (sample//self.div_sample_unit)*self.div_sample_unit
        return int(sample)

    def get_beat_pixels(self, start_pixel, end_pixel):
        start_pixel = (start_pixel//self.beat_pixel_unit)*self.beat_pixel_unit
        pixel = start_pixel
        while pixel<end_pixel:
            yield pixel
            pixel += self.beat_pixel_unit

    def get_div_pixels(self, start_pixel, end_pixel):
        start_pixel = (start_pixel//self.div_pixel_unit)*self.div_pixel_unit
        pixel = start_pixel
        while pixel<end_pixel:
            yield pixel
            pixel += self.div_pixel_unit
