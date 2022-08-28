"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import unicodedata

from common import *

# For the original Japanese version
_char_set = {}
for _base_idx, _chars in (
	(0, "あいうえおかきくけこさしすせそ\u3099"),
	(0x10, "たちつてとなにぬねのはひふへほ\u309a"),
	(0x20, "まみむめもやゆよらりるれろわをん"),
	(0x30, "アイウエオカキクケコサシスセソー"),
	(0x40, "タチツテトナニヌネノハヒフヘホ❜"),
	(0x50, "マミムメモヤユヨラリルレロワヲン"),
	(0x60, "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"),
	(0X84, "ゃっゅょャッュョ；：、。"),
	(0x96, "ぁぃぅぇぉ・？！※"),
	(0x9f, ("<heart>",)),
	(0xa6, "ァィゥェォ「」／％✕"),
	(0xbb, "［］〈〉"),
	(0xbf, ("<femblem>",)),
	(0xf0, "，〃´"),
	(0xff, "　"),
):
	_char_set.update({_base_idx + i: s for i, s in enumerate(_chars)})
_char_set.update(((ch, f"\\x{ch:02x}") for ch in (set(range(256)) - _char_set.keys())))

class TextData(TextDataBase):
	def __init__(self, rom, chr_start_offs):
		super().__init__(rom, chr_start_offs)

		leca = get_leca4((6, 15))
		self.item_class_equip_part_tbl = (c_uint8 * 9).from_buffer(rom, leca(0xa3d1))

		self.item_class_equip_idcs = []
		start_idx = 0
		for tbl_idx, end_idx in enumerate(self.item_class_equip_part_tbl):
			self.item_class_equip_idcs.extend([tbl_idx] * (end_idx - 1 - start_idx))

			start_idx = end_idx - 1
		self.item_class_equip_idcs.extend([0xfe] * (0x5c - start_idx))

		self.item_class_equip_tbl_addrs, self.item_class_equip_tbls = load_term_lists(
			rom, 
			leca, 
			0xa3da, 
			9, 
			terms = 0xef, 
			end_offs = chr_start_offs,
		)

	def get_script_iter(self, bank_idx, set_idx, script_idx):
		leca = get_leca4((bank_idx, 15))
		script_addr = self._script_addrs[bank_idx][set_idx][script_idx]
		script_offs = leca(script_addr)

		return iter((self._rom[script_offs:self._chr_start_offs],))

	def translate_text(self, text):
		return unicodedata.normalize("NFC", "".join((_char_set[ch] for ch in text)))

	_check_seqs = (
		(10, 0x81ea, 0x122, "3e2c9eb417227f003b1dec2a28a40246bcc0606f24efc15922fa168b05315114"),
		(15, 0xe69c, 0x16, "3e3742c4e1a0f485f98fe4bc9dca060e0eed7e6f880a445f8019a031ac864022"),
	)
