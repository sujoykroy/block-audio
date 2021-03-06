from audio_samples_instru import AudioSamplesInstru
from audio_file_block import AudioFileBlock, AudioFileClipSamples
import moviepy.editor as moviepy_editor
import os

class AudioFileInstru(AudioSamplesInstru):
    TYPE_NAME = "file"

    def __init__(self, filename, sample_count=None):
        self.filename = filename
        self.sample_count = sample_count
        self.base_block = None
        AudioSamplesInstru.__init__(
                    self,
                    None)
        self.amplitude = 1.
        self.set_name(os.path.basename(filename))

    def get_xml_element(self):
        elm = super(AudioFileInstru, self).get_xml_element()
        elm.attrib["filename"] = self.filename
        elm.attrib["amplitude"] = "{0}".format(self.amplitude)
        return elm

    @classmethod
    def create_from_xml(cls, elm):
        filename = elm.attrib.get("filename")
        if filename:
            newob = cls(filename)
            newob.load_from_xml(elm)
            newob.amplitude = float(elm.attrib.get("amplitude", 1.))
            return newob
        return None

    def get_base_block(self):
        if self.base_block is None:
            self.base_block = self.get_file_block()
        return self.base_block

    def set_amplitude(self, amplitude):
        if self.amplitude == amplitude:
            return
        self.amplitude = amplitude
        self.readjust_blocks()

    def get_file_block(self):
        return AudioFileBlock(self.filename, self.sample_count)

    def get_duration_seconds(self):
        if not os.path.isfile(self.filename):
            return 0.
        clip = moviepy_editor.AudioFileClip(self.filename)
        return clip.duration

    def get_samples_for(self, note):
        if self.samples is None:
            self.samples = self.get_base_block().get_full_samples()
        if isinstance(self.samples, AudioFileClipSamples):
            samples = self.samples
        else:
            samples = super(AudioFileInstru, self).get_samples_for(note)
        return samples*self.amplitude

    def set_filename(self, filename):
        self.filename = filename
        self.samples = None
        if self.base_block:
            self.base_block.set_filename(filename)
        self.readjust_blocks()

    @classmethod
    def load(cls, filepath, prefix='', recursive=True, test=False):
        if os.path.isdir(filepath):
            instru_list = []
            for filename in os.listdir(filepath):
                child_path = os.path.join(filepath, filename)
                if os.path.isdir(child_path):
                    if not recursive:
                        continue
                    else:
                        child_prefix = prefix + filename + "/"
                else:
                    child_prefix = prefix
                instru = cls.load(child_path, prefix=child_prefix)
                if instru:
                    instru_list.extend(instru)
            return instru_list
        if test:
            try:
                clip = moviepy_editor.AudioFileClip(filepath)
            except:
                clip = None
        else:
            clip = None
        if not test or (clip and clip.duration>0):
            del clip
            instru = AudioFileInstru(filepath)
            instru.set_name(prefix + os.path.splitext(os.path.basename(filepath))[0])
            return [instru]
        return None
