import threading
from audio_block import AudioBlock
from audio_group import AudioGroup
from audio_samples_block import AudioSamplesBlock
from ..commons import AudioMessage
import scipy.interpolate
import numpy
import time

class AudioKeypadBlock(AudioSamplesBlock):
    def __init__(self, samples, note):
        super(AudioKeypadBlock, self).__init__(samples)
        self.music_note = note
        self.loop = None

    def is_stopped(self):
        return self.current_pos >= self.duration

    def end_smooth(self):
        if self.is_stopped():
            return

        self.lock.acquire()
        if self.current_pos<self.inclusive_duration:
            start_pos = self.current_pos-20
            if start_pos<0:
                start_pos = 0
            seg = min(self.inclusive_duration-start_pos, int(self.SampleRate*.25))
            env_y =  [1, .75, .5, 0]
            env_x = numpy.round([0, seg*.25, seg*.5, seg-1])

            interp = scipy.interpolate.interp1d(env_x, env_y, bounds_error=False, kind="linear")
            xs = numpy.arange(0, seg)
            env = interp(xs).astype(numpy.float32)
            if len(self.samples.shape)>1:
                env = numpy.repeat(env, self.samples.shape[1]).reshape(-1, self.samples.shape[1])

            self.samples[start_pos:start_pos+seg, :] = \
                        self.samples[start_pos:start_pos+seg, :].copy()*env
            self.samples[start_pos+seg:, :] = 0
            self.duration = start_pos+seg
        else:
            self.duration = self.current_pos
        self.inclusive_duration = self.duration
        self.lock.release()
        #self.save_to_file("/home/sujoy/Temporary/end_smooth.wav")

class AudioKeypadGroup(AudioGroup):
    def __init__(self):
        super(AudioKeypadGroup, self).__init__()
        self.block_loop = None
        self.history = dict()
        self.record = False

    def set_record(self, value):
        self.record = value
        if not value:
            old_values = list(self.history.values())
            self.history.clear()
            return old_values
        return None

    def add_samples(self, samples, note, midi_channel, beat):
        block = AudioKeypadBlock(samples.copy(), note)
        block.set_no_loop()
        block.set_duration(self.SampleRate*60*10, beat)#10min
        if midi_channel>=0:
            block.set_midi_channel(midi_channel)
        self.add_block(block)
        if self.record:
            self.history[block.get_id()] = [block.music_note, time.time(), None]
        return block

    def get_samples(self, frame_count, loop=None):
        self.lock.acquire()
        block_count = len(self.blocks)
        self.lock.release()
        audio_message = super(AudioKeypadGroup, self).get_samples(frame_count)

        for i in xrange(block_count):
            self.lock.acquire()
            if i <len(self.blocks):
                block = self.blocks[i]
            else:
                block = None
            self.lock.release()

            if not block:
                break

            self.lock.acquire()
            if block.is_stopped():
                if self.record:
                    self.history[block.get_id()][2] = time.time()
                block.destroy()
            self.lock.release()

        return audio_message
