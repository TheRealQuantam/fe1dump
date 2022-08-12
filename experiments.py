"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import numpy as np
import PIL.Image
import PIL.ImagePalette
import time

Image = PIL.Image
ImagePalette = PIL.ImagePalette.ImagePalette

from common import *

def make_cmp_tables(texts):
	lower_word_counts = colls.defaultdict(int)
	upper_word_counts = colls.defaultdict(int)
	max_word_len = 16

	for text, op_infos in texts:
		text_len = len(text)
		if len(op_infos) < 2:
			continue

		prev_op_idx, prev_op_len = op_infos[1]

		for op_idx, op_len in op_infos[2:]:
			for word_idx in range (prev_op_idx + prev_op_len, op_idx):
				max_word_end = min(op_idx, word_idx + max_word_len)
				for word_end in range(word_idx + 3, max_word_end + 1):
					upper_word_counts[bytes(text[word_idx:word_end])] += 1

			prev_op_idx = op_idx
			prev_op_len = op_len

		for word_idx in range(text_len):
			max_word_end = min(text_len, word_idx + max_word_len)
			for word_end in range(word_idx + 3, max_word_end + 1):
				lower_word_counts[bytes(text[word_idx:word_end])] += 1

		a = 0

	for word_counts in (lower_word_counts, upper_word_counts):
		savings = [(word, ((count - 1) * (len(word) - 2) - 5)) for word, count in word_counts.items()]
		savings.sort(key = lambda x: -x[1])
		a = 0

	return

def run(rom, data):
	"""y = np.repeat(np.arange(0, 0x100, dtype = np.uint).reshape((-1, 1)), 0x400, 1)
	x = np.repeat(np.arange(0, 0x400, dtype = np.uint).reshape((1, -1)), 0x100, 0)

	cb = x & 0xff
	cd = x >> 8

	four = cb >> 3
	a = four.copy()
	six = cd << 5

	a = (a >> 2) | ((six & 0x80) >> 1) | ((a & 1) << 7)
	six <<= 1
	seven = a ^ (six & 0x80)
	five = ((seven >> 6) & 1) * 4 + 0x20

	a = y.copy()
	b = np.asarray(a >= 0xf0, dtype = np.uint)
	six = (six >> 1) | (b << 7)
	a += b << 4
	a >>= 3
	X = a.copy()

	a = (a >> 1) | (six & 0x80)
	six <<= 1
	a ^= (six & 0x80)
	five += (a & 0x80) >> 4

	res = ((five << 8) | four) + X * 0x20"""

	"""import threading
	make_webp = True
	threads = [threading.Thread(target = SaveAnimImages, args = (out_path.joinpath(f"metatiles{i}"), None, [frame.copy() for frame in frames], frame_times)) for i in range(1)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()"""

	"""def print_all_strs(bstr):
		end_offs = data._chr_start_offs
		if isinstance(bstr, str):
			bstr = bytes.fromhex(bstr)

		bank_addrs = colls.defaultdict(list)
		offs = rom.find(bstr, 0x10, end_offs)
		while offs >= 0:
			bank, addr = divmod(offs - 0x10, 0x4000)
			addr += 0x8000 if bank != 15 else 0xc000

			bank_addrs[bank].append(addr)

			offs = rom.find(bstr, offs + 1, end_offs)

		if bank_addrs:
			print(f"{bstr.hex()}:")

			for bank, addrs in bank_addrs.items():
				print(f"{bank:x}: " + " ".join((f"{addr:4x}" for addr in addrs)))

			print()

	print_all_strs("8df177")
	print_all_strs("8ef177")
	print_all_strs("8cf177")
	print_all_strs("8df477")
	print_all_strs("8ef477")
	print_all_strs("8cf477")
	print_all_strs("20819a")
	print_all_strs("4c819a")"""

	"""import text_polinym
	if isinstance(data.text, text_polinym.TextData):
		for bank_idx in range(16):
			leca = get_leca4((bank_idx, 15))
			raw_list_addrs = (c_uint16_le * 16).from_buffer(rom, leca(0xbfe0))
			list_addrs = list(filter(lambda x: (x != 0xffff), raw_list_addrs))

			checked_addrs = set()
			for set_idx, set_addr in enumerate(list_addrs):
				if set_addr in checked_addrs:
					continue

				checked_addrs.add(set_addr)

				script_addrs = (c_uint16_le * 2).from_buffer(rom, leca(set_addr))
				for script_idx, script_addr in enumerate(script_addrs):
					script_id = f"{bank_idx:x}:{set_idx:x}:{script_idx} ({script_addr:4x})"
					try:
						script_iter = text_polinym._ScriptInnerIterator(
							data._rom,
							data._chr_start_offs,
							leca(script_addr),
							data.text._dicts,
						)
						script, ops_offs = data._get_script(script_iter)

						print(f"{script_id}:")
						print(data.translate_text(script)[:300])

					except:
						print(f"FAILED TO PARSE: {script_id}")"""

	return