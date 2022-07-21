"""	
	fe1dump
	Dumping Utility for Fire Emblem: Shadow Dragon and the Blade of Light (NES)
	Copyright 2022 Justin Olbrantz (Quantam)

	This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License. To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.
"""

import numpy as np
import numpy.ma as ma
from pathlib import Path
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFile
import PIL.ImageFont
import PIL.ImagePalette
import sys

from common import *
from fe1data import *
import experiments

Image = PIL.Image
ImagePalette = PIL.ImagePalette.ImagePalette

def GetAnimatedMapFrames(data, map_idx, idx_is_data = False):
	pal_array = data.get_nes_palette_array(0)
	palette = ImagePalette("RGB", bytes(pal_array))
	mp = map_idx if idx_is_data else data.get_map_array(map_idx)

	frame_cache = {}
	frames = []
	frame_times = []
	for bank_idx, num_frames in data.map_anim_banks:
		img = frame_cache.get(bank_idx)
		if not img:
			chr_bank = data.get_chr_bank_array(bank_idx)
			bitmap = data.get_map_bitmap(chr_bank, mp)

			img = Image.fromarray(bitmap, "P")
			img.putpalette(palette)

			frame_cache[bank_idx] = img

		frames.append(img)
		frame_times.append(int(round(num_frames * 1000 / 60)))

	return frames, frame_times

def DrawMapStartLocations(frames, start_locs, font, color, outline_color):
	unique_frames = {id(frame): frame for frame in frames}
	for frame in unique_frames.values():
		draw = PIL.ImageDraw.Draw(frame)
		for idx, loc in enumerate(start_locs):
			drawtext = functools.partial(
				draw.text,
				(loc.x * 16 + 8, loc.y * 16 + 8),
				f"{idx + 1}",
				font = font,
				anchor = "mm",
			)

			drawtext(fill = outline_color, stroke_width = 2)
			drawtext(fill = color)

if __name__ == "__main__":
	def format_fn(stem, ext = None, number = None, is_anim = False):
		anim_str = " anim" if is_anim else ""
		num_str = f" {number}" if number is not None else ""
		ext_str = f".{ext}" if ext else ""

		if isinstance(stem, Path):
			return stem.parent.joinpath("".join((stem.name, anim_str, num_str, ext_str)))
		else:
			return "".join((stem, anim_str, num_str, ext_str))

	def SaveAnimGif(name, number, frames, frame_times):
		trans_idx = frames[0].info.get("transparency", -1)
		frames[0].save(format_fn(name, "gif", number), transparency = trans_idx, optimize = True)
		frames[0].save(
			format_fn(name, "gif", number, True), 
			transparency = trans_idx, 
			optimize = True, 
			save_all = True,
			append_images = frames[1:],
			duration = frame_times,
			loop = 0,
			disposal = 2,
			)

	def SaveAnimWebp(name, number, frames, frame_times):
		if frames[0].info["transparency"] >= 0:
			prev_frames = frames

			frames = []
			for prev_frame in prev_frames:
				frame = prev_frame.copy()
				frame.apply_transparency()

				frames.append(frame)

		frames[0].save(
			format_fn(name, "webp", number, True),
			lossless = True, 
			quality = 100, 
			method = 6,
			minimize_size = True,
			save_all = True,
			append_images = frames[1:],
			duration = frame_times,
			loop = 0,
			)

	def SaveAnimImages(name, number, frames, frame_times):
		SaveAnimGif(name, number, frames, frame_times)
		if make_webp:
			SaveAnimWebp(name, number, frames, frame_times)

	rom = bytearray(Path(sys.argv[1]).read_bytes())
	out_path = Path("out")
	out_path.mkdir(exist_ok = True)

	data = FireEmblem1Data(rom)

	pal_array = data.get_nes_palette_array(0)
	remap_pal = data.get_remap_palette_array(pal_array, True)
	palette = ImagePalette("RGB", bytes(pal_array))

	make_webp = False
	a = 0

	leca = data.miss_info_leca
	bank_set = data.pre_miss_script_bank_set
	pre_miss_infos = [data.get_pre_miss_info(idx + 1) for idx in range(len(data.pre_miss_info_addrs))]
	pre_miss_scripts = {bank_set + (info.dialog_idx,): i + 1 for i, info in enumerate(pre_miss_infos)}

	bank_set = data.miss_dlg_script_bank_set
	miss_dlgs = []
	miss_dlg_scripts = colls.defaultdict(set)
	for map_idx in range(len(data.miss_dlg_addrs)):
		infos = data.get_miss_dlg_info(map_idx + 1)
		miss_dlgs.append(infos)

		for i, info in enumerate(infos):
			miss_dlg_scripts[bank_set + (info.dialog_idx,)].add((map_idx, i))

	script_addrs = data.get_script_addrs()
	op_suffixes = {
		ScriptOps.RunScript: "\n", 
		ScriptOps.RunScriptForOtherParticipant: "\n", 
		ScriptOps.Interact: "\n", 
		ScriptOps.EndOfLine: "\n", 
		ScriptOps.PauseForInput: "\n\n", 
		ScriptOps.EndScript: "\n",
	}
	next_scripts = {}
	prev_scripts = colls.defaultdict(set)
	scripts = colls.OrderedDict()
	all_texts = {}

	for bank_idx, bank_sets in script_addrs.items():
		for set_idx, bank_set in enumerate(bank_sets):
			for script_idx in range(len(bank_set)):
				script_id = (bank_idx, set_idx, script_idx)

				script_info = data.get_script(bank_idx, set_idx, script_idx)
				script = bytes(script_info.script)
				ops_offs = script_info.op_infos
				scripts[script_id] = script_info
				all_texts[script_addrs[bank_idx][set_idx][script_idx]] = (script, ops_offs)

				op_offs = ops_offs[-1][0]
				if script[op_offs] in (ScriptOps.RunScript, ScriptOps.RunScriptForOtherParticipant):
					bank_set, next_idx = script[op_offs + 1:op_offs + 3]
					new_id = (bank_set >> 4, bank_set & 0xf, next_idx)

					next_scripts[script_id] = new_id
					prev_scripts[new_id].add(script_id)

	for script_id, script_info in scripts.items():
		script = script_info.script

		pre_miss = pre_miss_scripts.get(script_id)
		pre_miss_str = f", pre: {pre_miss:x}" if pre_miss is not None else ""

		miss_dlgs = miss_dlg_scripts.get(script_id)
		miss_dlg_str = ""
		if miss_dlgs:
			miss_dlg_str = ", dialog: " + " ".join((f"({info[0]:x}, {info[1]:x})" for info in miss_dlgs))

		parts = [f"{bidx:x}:{gidx:x}:{sidx:x}" for bidx, gidx, sidx in prev_scripts.get(script_id, ())]
		prev_script_str = ""
		if parts:
			prev_script_str = ", prev: " + " ".join(parts)

		id_str = ":".join((f"{idx:x}" for idx in script_id))
		print(f"SCRIPT {id_str}{pre_miss_str}{miss_dlg_str}{prev_script_str}:")

		parts = []
		cur_offs = 0
		for op_offs, op_len in script_info.op_infos:
			if op_offs != cur_offs:
				part = script[cur_offs:op_offs]
				xlated = data.translate_text(part)
				parts.append(xlated)

			cur_offs = op_offs + op_len

			suffix = op_suffixes.get(script[op_offs], "")
			parts.append(f"<{script[op_offs:cur_offs].hex()}>{suffix}")

		print("".join(parts))

	#experiments.make_cmp_tables(all_texts.values())
	experiments.run(rom)

	mp = np.arange(0, 256, 1, np.uint8).reshape((16, 16))
	frames, frame_times = GetAnimatedMapFrames(data, mp, True)
	frames[0].save(out_path.joinpath("metatiles.png"))

	SaveAnimImages(out_path.joinpath("metatiles"), None, frames, frame_times)

	sprite_pal = data.get_palette_array(0, True)
	sprite_palette = ImagePalette("RGB", bytes(nes_pal[sprite_pal]))

	chr_banks = {}
	num_sprites = len(data.map_sprites)
	num_colors = len(data.map_sprite_pal_idcs)
	num_facings = len(SpriteFacing)
	num_frames = 2
	size = 48
	sprite_bmps = ma.masked_all((
		num_sprites, 
		num_colors, 
		num_facings, 
		num_frames, 
		size, 
		size,
		), dtype = np.uint8)
	for sprite_idx, sprite_info in enumerate(data.map_sprites):
		chr_bank = chr_banks.get(sprite_info.chr_bank_idx)
		if chr_bank is None:
			chr_bank = data.get_chr_bank_array(sprite_info.chr_bank_idx)
			chr_banks[sprite_info.chr_bank_idx] = chr_bank

		sprite_tbl = sprite_info.sprite_tbl
		frame_idcs = sprite_info.frame_idcs
		flip_right = sprite_info.right_facing_is_flipped

		for team_idx, pal_idx in enumerate(data.map_sprite_pal_idcs):
			for facing in range(num_facings):
				data.draw_sprite_frames(
					sprite_bmps[sprite_idx][team_idx][facing], 
					chr_bank, 
					[sprite_tbl[idx] for idx in frame_idcs[facing]], 
					size // 2, 
					size // 2, 
					pal_idx = pal_idx, 
					hflipped = flip_right and facing == SpriteFacing.Right,
			)

	bitmaps = sprite_bmps.reshape((-1, num_colors, num_facings, num_frames, size, size)).transpose((3, 0, 4, 1, 2, 5)).reshape((num_frames, num_sprites * size, -1))
	bitmaps2 = np.zeros_like(bitmaps)

	line_color = 1
	num_frames, height, width = bitmaps.shape
	for x in range(0, width + 1, size):
		bitmaps2[:, :, max(x - 1, 0):min(x + 1, width)] = line_color
	for y in range(0, height + 1, size):
		bitmaps2[:, max(y - 1, 0):min(y + 1, height), :] = line_color

	bitmaps = ma.choose(bitmaps.mask, (bitmaps, bitmaps2))

	frames = []
	for bitmap in bitmaps:
		img = Image.fromarray(bitmap.filled(0), "P")
		img.putpalette(sprite_palette)
		img.info["transparency"] = 0

		frames.append(img)

	SaveAnimImages(out_path.joinpath("map sprites"), None, frames, (400, 400))

	for port_idx, port in enumerate(data.port_infos):
		bitmap = data.draw_portrait(port)
		pal = data.get_port_palette_array(port.pal_idx)
		frame_times = [int(round(x * 1000 / 60)) for x in port.frame_times]
		frames = []
		big_frames = []
		for frame in bitmap:
			img = Image.fromarray(frame.filled(0), "P")
			img.putpalette(ImagePalette("RGB", bytes(nes_pal[pal])))
			frames.append(img)
			big_frames.append(img.resize((img.width * 4, img.height * 4), Image.Resampling.NEAREST))
	
		SaveAnimImages(out_path.joinpath("portrait"), port_idx, frames, frame_times)
		SaveAnimImages(out_path.joinpath("portrait big"), port_idx, big_frames, frame_times)

	font = PIL.ImageFont.truetype("arialbd.ttf", 11)

	for map_idx in sorted(data.maps):
		mp = data.get_map_array(map_idx)
		frames, frame_times = GetAnimatedMapFrames(data, mp, True)

		SaveAnimImages(out_path.joinpath("map"), map_idx, frames, frame_times)

		np_objs, pc_objs = data.get_map_objs(map_idx)
		mp = data.merge_map_array_with_objs(mp, np_objs, pc_objs)
		frames, frame_times = GetAnimatedMapFrames(data, mp, True)

		if map_idx > 1:
			DrawMapStartLocations(frames, data.map_start_loc_lists[map_idx], font, 1, 0)

		SaveAnimImages(out_path.joinpath("map objs"), map_idx, frames, frame_times)
	
	a = 1