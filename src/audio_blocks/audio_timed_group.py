from audio_block import AudioBlock, AudioBlockTime
import threading
import time
import numpy
from ..commons import AudioMessage
from xml.etree.ElementTree import Element as XmlElement
import moviepy.editor
from ..commons import WaveFileWriter
import os

class AudioTimedGroup(AudioBlock):
    TYPE_NAME = "tgrp"

    blank_data = None
    def __init__(self):
        super(AudioTimedGroup, self).__init__()
        self.blocks = []
        self.linked_to = None
        self.linked_copies = None
        self.lock = threading.RLock()
        if AudioTimedGroup.blank_data is None:
            AudioTimedGroup.blank_data = self.get_blank_data(AudioBlock.FramesPerBuffer)

    def copy(self, linked=False):
        if self.linked_to:
            newob = self.linked_to.copy(linked=True)
            self.copy_values_into(newob)
            return newob
        newob = type(self)()
        self.copy_values_into(newob)
        if linked:
            if self.linked_copies is None:
                self.linked_copies = []
            self.linked_copies.append(newob)
            newob.linked_to = self
            newob.blocks = self.blocks
            newob.lock = self.lock
        else:
            for block in self.blocks:
                newob.blocks.append(block.copy())
        return newob

    @classmethod
    def create_from_xml(cls, elm, blocks, linked_to):
        newob = cls()
        newob.load_from_xml(elm)
        newob.linked_to = linked_to
        if linked_to:
            if linked_to.linked_copies is None:
                linked_to.linked_copies = []
            linked_to.linked_copies.append(newob)
            newob.inclusive_duration = linked_to.inclusive_duration
            newob.blocks = linked_to.blocks
        else:
            newob.blocks.extend(blocks)
            for block in blocks:
                block.set_owner(newob)
            newob.calculate_duration()
        return newob

    def destroy(self):
        self.linked_to = None
        if self.linked_copies:
            for linked_block in self.linked_copies:
                linked_block.destroy()
            del self.linked_copies[:]
        super(AudioTimedGroup, self).destroy()

    def get_xml_element(self):
        elm = super(AudioTimedGroup, self).get_xml_element()
        elm.attrib["type"] = self.TYPE_NAME
        if self.linked_to:
            elm.attrib["linked_to"] = self.linked_to.get_name()
        else:
            for i in xrange(len(self.blocks)):
                block = self.blocks[i]
                elm.append(block.get_xml_element())
        return elm

    def has_block_linked_to(self, linked_to):
        for block in self.blocks:
            if isinstance(block, AudioTimedGroup):
                if block.linked_to == linked_to:
                    return True
        return False

    def recompute_time(self, beat):
        if self.linked_to:
            self.linked_to.recompute_time(beat)
        else:
            for block in self.blocks:
                block.recompute_time(beat)
            self.calculate_duration()
        super(AudioTimedGroup, self).recompute_time(beat)

    def add_block(self, block, at, unit, beat):
        ret = True
        self.lock.acquire()
        if block not in self.blocks:
            self.blocks.append(block)
        else:
            ret = False
        block.set_owner(self)
        block.start_time.set_unit(unit, beat)
        block.start_time.set_value(at, beat)
        self.lock.release()
        self.calculate_duration()
        return ret

    def add_block_direct(self, block):
        if block not in self.blocks:
            self.blocks.append(block)
            block.set_owner(self)

    def remove_block(self, block):
        self.lock.acquire()
        if block in self.blocks:
            index = self.blocks.index(block)
            block.set_owner(None)
            del self.blocks[index]
        self.lock.release()
        self.calculate_duration()

    def set_block_name(self, block, name):
        for existing_block in self.blocks:
            if existing_block.get_name() == name:
                return False
        block.set_name(name)

    def get_block_position(self, block):
        return block.start_time.sample_count

    def get_block_position_value(self, block):
        return block.start_time.value

    def get_block_position_unit(self, block):
        return block.start_time.unit

    def set_block_position_value(self, block, value, beat):
        self.lock.acquire()
        block.start_time.set_value(value, beat)
        self.lock.release()
        self.calculate_duration()

    def set_block_position_unit(self, block, unit, beat):
        self.lock.acquire()
        block.start_time.set_unit(unit, beat)
        self.lock.release()
        self.calculate_duration()

    def set_block_position(self, block, sample_count, beat):
        self.lock.acquire()
        block.start_time.set_sample_count(sample_count, beat)
        self.lock.release()
        self.calculate_duration()

    def stretch_block_to(self, block, sample_count, beat):
        self.lock.acquire()
        start_pos = block.start_time.sample_count
        block.set_duration(sample_count-start_pos, beat)
        self.lock.release()
        self.calculate_duration()

    def calculate_duration(self):
        self.lock.acquire()
        block_count = len(self.blocks)
        self.lock.release()

        duration = 0
        for i in xrange(block_count):
            self.lock.acquire()
            if i<len(self.blocks):
                block = self.blocks[i]
                block_start_pos = block.start_time.sample_count
            else:
                block = None
            self.lock.release()

            if not block:
                break

            end_at = block_start_pos+block.duration
            if end_at>duration:
                duration = end_at
        self.inclusive_duration = duration
        super(AudioTimedGroup, self).calculate_duration()

        if self.linked_copies:
            for linked_block in self.linked_copies:
                linked_block.inclusive_duration = self.inclusive_duration

    def get_samples(self, frame_count, start_from=None, use_loop=True, loop=None, pausable=True):
        if self.paused and pausable:
            return None
        self.lock.acquire()
        block_count = len(self.blocks)
        self.lock.release()
        if start_from is None:
            start_pos = self.current_pos
        else:
            start_pos = int(start_from)

        if loop is None:
            loop = self.loop
            full_duration = self.inclusive_duration
        else:
            full_duration = self.duration

        audio_message = AudioMessage()
        if loop and use_loop:
            data = None
            spread = frame_count
            data_count = 0
            while data is None or data.shape[0]<frame_count:
                if loop == self.LOOP_STRETCH:
                    if start_pos>=self.duration:
                        break
                    read_pos = start_pos%full_duration
                else:
                    start_pos %= full_duration
                    read_pos = start_pos

                if read_pos+spread>full_duration:
                    read_count = full_duration-read_pos
                else:
                    read_count = spread
                seg_message = self.get_samples(read_count, start_from=read_pos, use_loop=False)
                if seg_message is None:
                    continue
                if seg_message.midi_messages:
                    for midi_message in seg_message.midi_messages:
                        midi_message.increase_delay(data_count)
                    audio_message.midi_messages.extend(seg_message.midi_messages)
                if seg_message.block_positions:
                    audio_message.block_positions.extend(seg_message.block_positions)

                seg_samples = seg_message.samples
                if data is None:
                    data = seg_samples
                else:
                    data = numpy.append(data, seg_samples, axis=0)
                start_pos += seg_samples.shape[0]
                data_count += seg_samples.shape[0]
                spread -= seg_samples.shape[0]

            if start_from is None:
                self.current_pos = start_pos

            if data is None:
                data = self.blank_data[:frame_count, :]
            elif data.shape[0]<frame_count:
                blank_shape = (frame_count - data.shape[0], AudioBlock.ChannelCount)
                data = numpy.append(data, numpy.zeros(blank_shape, dtype=numpy.float32), axis=0)

            audio_message.block_positions.append([self, start_pos])
            audio_message.samples = data
            return audio_message

        samples = None
        for i in xrange(block_count):
            block_samples = None
            self.lock.acquire()
            if i<len(self.blocks):
                block = self.blocks[i]
                block_start_pos = block.start_time.sample_count
            else:
                block = None
            self.lock.release()

            if not block:
                break
            if start_pos+frame_count<block_start_pos:
                continue

            if block.loop == self.LOOP_INFINITE:
                if block_start_pos<start_pos:
                    elapsed = start_pos-block_start_pos
                    block_start_pos += (elapsed//block.duration)*block.duration
                    block_start_pos = int(block_start_pos)
            elif block_start_pos+block.duration<start_pos:
                continue

            if block_start_pos>start_pos:
                block_samples = self.blank_data[:block_start_pos-start_pos, :]
                block_start_from = 0
                sub_frame_count = start_pos + frame_count-block_start_pos
            else:
                block_samples = None
                block_start_from = start_pos-block_start_pos
                sub_frame_count = frame_count

            seg_message = block.get_samples(sub_frame_count, start_from=block_start_from)
            if seg_message.midi_messages:
                audio_message.midi_messages.extend(seg_message.midi_messages)
            if seg_message.block_positions:
                audio_message.block_positions.extend(seg_message.block_positions)

            if block_samples is None:
                block_samples = seg_message.samples
            else:
                block_samples = numpy.append(block_samples, seg_message.samples, axis=0)

            if samples is None:
                samples = block_samples
            else:
                samples  = samples + block_samples

        if  samples is None:
            samples = self.blank_data[:int(frame_count), :]

        start_pos += frame_count

        if start_from is None:
            self.current_pos = start_pos
            if self.current_pos>self.duration:
                self.current_pos = self.duration

        audio_message.block_positions.append([self, start_pos])
        audio_message.samples = samples
        return audio_message

    def get_instru_set(self):
        if self.linked_to:
            return None
        instru_set = set()
        for block in self.blocks:
            block_instru_set = block.get_instru_set()
            if not block_instru_set:
                continue
            instru_set = instru_set.union(block_instru_set)
        return instru_set

    def save_to_file(self, filename):
        wave_filename = filename + ".wav.temp" + str(time.time())
        wave_file_writer = WaveFileWriter(wave_filename, sample_rate=AudioBlock.SampleRate)
        buffer_size = AudioBlock.FramesPerBuffer
        for i in xrange(0, self.duration_time.sample_count, buffer_size):
            frame_count = min(self.duration_time.sample_count-i, buffer_size)
            audio_message = self.get_samples(frame_count, start_from=i, use_loop=False, pausable=False)
            wave_file_writer.write(audio_message.samples)
        wave_file_writer.close()
        audio_clip = moviepy.editor.AudioFileClip(wave_filename)
        audio_clip.write_audiofile(filename, fps=int(AudioBlock.SampleRate))
        del audio_clip
        os.remove(wave_filename)

    def get_description(self):
        if self.linked_to:
            return self.linked_to.get_description()
        return self.name
