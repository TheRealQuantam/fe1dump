"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

from common import *

# This is for https://www.romhacking.net/translations/6087/. Other translations will undoubtedly use different character sets.
_char_set = {}
for _base_idx, _chars in (
	(0, "ABCDEFGHIJKLMNO"),
	(0x10, "QRSTUVWXYZabcdefghijklmnopqrstuvwxyz!?.,-'"), # This ' is left-aligned
	(0x3a, ("<bolt>", "<ring>", "<shield>", "C", "<key>", "<low-->", "<tr-N>", "<tr-G>", "<tr-P>")),
	(0x44, ("…", "<sword>", "<spear>", "<bow>", "<axe>", "<staff>", "<orb1>", "<book>")),
	(0x4c, "“”"),
	(0x4e, ("ll", "<center-'>")), # This ' is centered
	(0x50, "Pf…"),
	(0x53, ("li", "il", "<orb2>", "<orb3>", "<rod>")),
	(0x58, [f"<tr-{ch}>" for ch in "SARD"]),
	(0x5c, "K"),
	(0x5d, [f"<tr-{ch}>" for ch in "MFJ"]),
	(0x60, "0123456789"),
	(0x6a, [f"<low-{ch}>" for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]),
	(0x84, " ERAINT"),
	(0X8c, ";:"),
	(0x93, ("<low-.>",)),
	(0x9b, ("<dot>", "<low-?>", "<low-!>")),
	(0x9e, ("<bullet>", "<heart>")),
	(0xad, "/%"),
	(0xaf, ("<cross>",)),
	(0xbb, "[]()"),
	(0xbf, ("<femblem>",)),
):
	_char_set.update({_base_idx + i: s for i, s in enumerate(_chars)})
_char_set.update(((ch, f"\\x{ch:02x}") for ch in (set(range(256)) - _char_set.keys())))

DictEntry = namedtuple("DictEntry", ("tbl", "leca"))

class _ScriptInnerIterator:
	_uncmp_re = re.compile(rb"\x8e|\x8f")
	_word_re = re.compile(rb"\xef")

	def __init__(self, rom, rom_size, script_offs, dicts):
		self._rom = rom
		self._rom_size = rom_size
		self._dicts = dicts
		self._abs_offs = script_offs
		self._offs = 0

		self.total_bytes = 0
		self.cmp_bytes = 0

		self._hdlrs = {
			0x8e: functools.partial(self._hdl_dict, 0),
			0x8f: functools.partial(self._hdl_dict, 1),
		}

		return
	
	def __iter__(self):
		return self

	def __next__(self):
		byte = self._rom[self._abs_offs]
		return self._hdlrs.get(byte, self._hdl_text)()

	def _hdl_dict(self, dict_idx):
		rom = self._rom
		dic = self._dicts[dict_idx]
		word_idx = rom[self._abs_offs + 1] & 0x7f
		word_offs = dic.leca(dic.tbl[word_idx])

		match = _ScriptInnerIterator._word_re.search(rom, word_offs)

		text_len = match.start() - word_offs
		self._abs_offs += 2
		self._offs += 2
		self.total_bytes += text_len
		self.cmp_bytes += text_len - 2

		return (c_char * text_len).from_buffer(rom, word_offs)

	def _hdl_text(self):
		rom = self._rom
		abs_offs = self._abs_offs
		rom_size = self._rom_size

		match = _ScriptInnerIterator._uncmp_re.search(rom, abs_offs)

		text_len = match.start() - abs_offs
		self._abs_offs += text_len
		self._offs += text_len
		self.total_bytes += text_len

		return (c_char * text_len).from_buffer(rom, abs_offs)

class TextData(TextDataBase):
	def __init__(self, rom, chr_start_offs):
		super().__init__(rom, chr_start_offs)

		dict_pos = ((0, 0xb5a0, 0x80), (8, 0xdea0, 0xc7))
		self._dicts = []
		for bank_idx, addr, length in dict_pos:
			leca = get_leca4((bank_idx, 15))
			offs = leca(addr)
			
			tbl = (c_uint16_le * length).from_buffer(rom, offs)
			self._dicts.append(DictEntry(tbl, leca))

		leca = get_leca4((6, 15))
		self.item_class_equip_idcs = (c_uint8 * num_items).from_buffer(rom, leca(0xfe58 + 1))
		self.item_class_equip_tbl_addrs, self.item_class_equip_tbls = load_term_lists(
			rom, 
			leca, 
			0xa3d4, 
			12, 
			terms = 0xef, 
			end_offs = chr_start_offs,
		)

		return

	def get_script_iter(self, bank_idx, set_idx, script_idx):
		leca = get_leca4((bank_idx, 15))
		script_addr = self._script_addrs[bank_idx][set_idx][script_idx]
		script_offs = leca(script_addr)

		return _ScriptInnerIterator(
			self._rom,
			self._chr_start_offs,
			script_offs,
			self._dicts,
		)

	def translate_text(self, text):
		return "".join((_char_set[ch] for ch in text))

	_check_seqs = (
		(10, 0x81ea, 0x122, "3e2c9eb417227f003b1dec2a28a40246bcc0606f24efc15922fa168b05315114"),
		(15, 0xe69c, 0xd, "e5d38d48df5f5df7f204ef0bd4ee1c847d1ee4a60befcb647f501f0eb0183a70"),
		(15, 0xfcf0, 0xc6, "91c7359bd124112123269396547b8678f9415abad2642cba52c3fc14237ad2c2"),
		(15, 0xff80, 9, "77d7fe1c7f34ab1c676ad4abae782132806598cc4c2e752aebc952938d43a460"),
	)
