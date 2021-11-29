import os

import librosa.display as lbd
import matplotlib.pyplot as plt
import sounddevice
import soundfile
import torch

from InferenceInterfaces.InferenceArchitectures.InferenceHiFiGAN import HiFiGANGenerator
from InferenceInterfaces.InferenceArchitectures.InferenceTacotron2 import Tacotron2
from Preprocessing.TextFrontend import TextFrontend


class aridialect_Tacotron2(torch.nn.Module):

    def __init__(self, device="cpu", speaker_embedding=None):
        super().__init__()
        self.speaker_embedding = speaker_embedding
        self.device = device
        if isinstance(speaker_embedding, torch.Tensor):
            self.speaker_embedding = speaker_embedding
        else:
            self.speaker_embedding = torch.load(os.path.join("Models", "SpeakerEmbedding", speaker_embedding), map_location='cpu').to(
                torch.device(device)).squeeze(0).squeeze(0)
        self.text2phone = TextFrontend(language="at-lab", use_word_boundaries=False,
                                       use_explicit_eos=False, inference=True)
        self.phone2mel = Tacotron2(path_to_weights=os.path.join("Models", "Tacotron2_aridialect", "best.pt"),
                                   idim=166, odim=80, spk_embed_dim=960, reduction_factor=1).to(torch.device(device))
        self.mel2wav = HiFiGANGenerator(path_to_weights=os.path.join("Models", "HiFiGAN_aridialect", "best.pt")).to(torch.device(device))
        self.phone2mel.eval()
        self.mel2wav.eval()
        self.to(torch.device(device))

    def forward(self, text, view=False, path_to_wavfile):
        with torch.no_grad():
            phones = self.text2phone.string_to_tensor(text,view,path_to_wavfile=path_to_wavfile).squeeze(0).long().to(torch.device(self.device))
            mel = self.phone2mel(phones, speaker_embedding=self.speaker_embedding).transpose(0, 1)
            wave = self.mel2wav(mel)
        if view:
            fig, ax = plt.subplots(nrows=2, ncols=1)
            ax[0].plot(wave.cpu().numpy())
            lbd.specshow(mel.cpu().numpy(), ax=ax[1], sr=16000, cmap='GnBu', y_axis='mel', x_axis='time', hop_length=256)
            ax[0].set_title(self.text2phone.get_phone_string(text,False, path_to_wavfile))
            ax[0].yaxis.set_visible(False)
            ax[1].yaxis.set_visible(False)
            plt.subplots_adjust(left=0.05, bottom=0.1, right=0.95, top=.9, wspace=0.0, hspace=0.0)
            plt.show()

        return wave

    def read_to_file(self, wav_list, file_location, silent=False):
        """
        :param silent: Whether to be verbose about the process
        :param text_list: A list of strings to be read
        :param file_location: The path and name of the file it should be saved to
        """
        wav = None
        silence = torch.zeros([24000])
        i=0
        for wavname in wav_list:
            if wavname.strip() != "":
                if not silent:
                    print("Now synthesizing: {}".format(wavname))
                if wav is None:
                    wav = self("",False,wavname).cpu()
                    wav = torch.cat((wav, silence), 0)
                else:
                    wav = torch.cat((wav, self("",False,wavname).cpu()), 0)
                    wav = torch.cat((wav, silence), 0)
                i=i+1
        soundfile.write(file=file_location, data=wav.cpu().numpy(), samplerate=48000)

    def read_aloud(self, wavname, view=False, blocking=False):
        if wavname.strip() == "":
            return
        wav = self("",False,wavname).cpu()
        #wav = self(text, view).cpu()
        wav = torch.cat((wav, torch.zeros([24000])), 0)
        if not blocking:
            sounddevice.play(wav.numpy(), samplerate=48000)
        else:
            sounddevice.play(torch.cat((wav, torch.zeros([12000])), 0).numpy(), samplerate=48000)
            sounddevice.wait()

    def plot_attention(self, wavname):
        sentence_tensor = self.text2phone.string_to_tensor("",False,path_to_wavfile=wavname).squeeze(0).long().to(torch.device(self.device))
        att = self.phone2mel(text=sentence_tensor, speaker_embedding=self.speaker_embedding, return_atts=True)
        fig, axes = plt.subplots(nrows=1, ncols=1)
        axes.imshow(att.detach().numpy(), interpolation='nearest', aspect='auto', origin="lower")
        axes.set_title("{}".format(sentence))
        axes.xaxis.set_visible(False)
        axes.yaxis.set_visible(False)
        plt.tight_layout()
        plt.show()

    def save_embedding_table(self):
        import json
        phone_to_embedding = dict()
        for phone in self.text2phone.ipa_to_vector:
            if phone in ['?', 'ɚ', 'p', 'u', 'ɹ', 'ɾ', 'ʔ', 'j', 'l', 'ɔ', 'v', 'm', '~', 'ᵻ', 'ɪ', 'ʒ', 'æ', 'n', 'z', 'ŋ', 'i', 'b', 'o', 'ɛ', 'e', 't', '!',
                         'ʊ', 'ð', 'd', 'θ',
                         'ɑ', 'ɡ', 's', 'ɐ', 'k', 'w', 'ə', 'ʌ', 'ʃ', '.', 'a', 'ɜ', 'h', 'f']:
                print(phone)
                phone_to_embedding[phone] = self.phone2mel.enc.embed(torch.LongTensor([self.text2phone.ipa_to_vector[phone]])).detach().numpy().tolist()
        with open("embedding_table_512dim.json", 'w', encoding="utf8") as fp:
            json.dump(phone_to_embedding, fp)
