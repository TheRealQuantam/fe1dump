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

dec_re = re.compile(r"(\d+)")
fmt_esc_re = re.compile(r"([\{\}])")
fmt_spec_re = re.compile(r"^ ( [^:]* ) : ( [^:]+ ) : ( [^:\.]* \d+ [^:]* ) $", re.X)

unit_abbrevs = "SK AK PK Pl DK Mr Ft Pr Th Hr Ar Hn Sh HM Sn Cm Mk Mg Cl Bi Ld Gn".split()
ext_unit_abbrevs = unit_abbrevs + "Dr ED".split()

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
	rom = bytearray(Path(sys.argv[1]).read_bytes())
	out_path = Path("out")
	out_path.mkdir(exist_ok = True)

	data = FireEmblem1Data(rom)

	make_webp = False
	font10 = font = PIL.ImageFont.truetype("arialbd.ttf", 10)
	font = PIL.ImageFont.truetype("arialbd.ttf", 11)

	if isinstance(data.text, text_original.TextData):
		class StdOut:
			_char_map = str.maketrans(dict(
				[(" ", "　")] + [(chr(idx), chr(0xfee0 + idx)) 
					for idx in range(0x21, 0x7e)]
			))

			def __init__(self, out):
				self._out = out

			def write(self, s):
				self._out.write(s.translate(StdOut._char_map))

		sys.stdout = StdOut(sys.stdout)
		sys.stderr = StdOut(sys.stderr)

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

	def save_images(name, number, img):
		path = format_fn(Path(name), None, number)
		img.save(path.with_suffix(".gif"))
		if make_webp:
			img.save(
				path.with_suffix(".webp"), 
				lossless = True,
				quality = 100, 
				method = 6,
			)

	def get_flag_str(flags, flag_names):
		bit_str = f"{flags:08b}"

		zero_ord = ord("0")
		flag_parts = [(flag_names[i] if ch == "1" else "-") for i, ch in enumerate(bit_str)]
		return "".join(flag_parts)

	def prepare_print_table(tbl_fmt, data_idx = -1, *, prefix = "", args = {}):
		fmt_parts = []
		val_names = []
		num_args = []
		for idx, info in enumerate(tbl_fmt):
			if isinstance(info, str):
				name, sym, fmt = fmt_spec_re.fullmatch(info).groups()
			else:
				name, sym, fmt = info

			width = int(dec_re.search(fmt)[0])
			match = dec_re.fullmatch(sym)
			if match:
				num_args.append(int(match[0]))

			val_names.append(name + " " * (width - len(name)))
			fmt_parts.append(f"{{{sym}:{fmt}}}")

		if data_idx > 0:
			idx = data_idx - 1
			val_names[idx] += " "
			fmt_parts[idx] += ":"

		return {
			"hdr": prefix + " ".join(val_names),
			"fmt": (fmt_esc_re.sub(r"\1\1", prefix) + " ".join(fmt_parts)).format,
			"num_num_args": max(num_args) + 1 if num_args else 0,
			"args": args,
		}

		return (hdr, fmt)

	def format_table(tbl_fmt, tbl, *, base_idx = 0):
		hdr = tbl_fmt["hdr"]
		fmt = tbl_fmt["fmt"]
		num_num_args = tbl_fmt["num_num_args"]
		args = tbl_fmt["args"]

		if num_num_args:
			return hdr, [fmt(*entry[1:], **args, e = entry[0], idx = idx + base_idx) for idx, entry in enumerate(tbl)]
		else:
			return hdr, [fmt(**args, e = entry, idx = idx + base_idx) for idx, entry in enumerate(tbl)]

	def print_table(tbl_fmt, tbl, *, base_idx = 0):
		hdr, lines = format_table(tbl_fmt, tbl, base_idx = base_idx)
		print(hdr)
		for line in lines:
			print(line)

		print()

	gold_action_amounts = [1000, 2000, 5000, 10000, 15000, 20000, 30000, 50000]
	simple_action_strs = colls.defaultdict(lambda x = 0: "Give Fire Emblem", {
		0x80: "Add first character to party",
		0x81: "If 26 {pc_names[38]} not in party add first character to party",
		0x82: "If 27 {pc_names[39]} not in party add second character to party",
		0x83: "If 2 {pc_names[2]} in party do dialog 51 instead",
		0x84: "If Star/Light orbs acquired give {item_names[53]}",
	})

	def get_dlg_action_str(pc_names, item_names, action):
		if action < 0x80:
			if not action:
				return ""
			elif action < 0x78:
				return f"Give {action:x} {item_names[action]}"
			else:
				return f"Give {gold_action_amounts[action - 0x78]}G"
		else:
			fmt_str = simple_action_strs[action]
			return fmt_str.format(pc_names = pc_names, item_names = item_names)

	def get_unit_items_str(item_names, num_items, obj):
		parts = []

		for item_idx in range(num_items):
			item_num = obj.item_idcs[item_idx]
			item_name = f"{item_names[item_num]}" if item_num else "None"
			parts.append(f"{item_idx}: {item_num} {item_name} ({obj.item_values[item_idx]})")

		for idx in range(num_items, len(obj.item_values)):
			value = obj.item_values[idx]
			parts.append(f"{idx}: {value}")

		return ", ".join(parts)

	def dump_unit_types():
		print("Enemy Unit Type Base Stats:")

		stat_names = "Str Skl Wpn Spd Lck Def Mov HP Exp".split()
		unit_names = list(map(data.translate_text, data.unit_names))
		name_len = max(map(len, unit_names))

		parts = [f"{name:>4}" for name in stat_names]
		print(" " * (name_len + 4) + "".join(parts))

		for idx, char_stats in enumerate(data.unit_type_infos):
			name = unit_names[idx]
			name += ":" + " " * (name_len - len(name))
			parts = [
				f"{x:4d}" 
				for x in (c_uint8 * sizeof(char_stats)).from_buffer(char_stats)
			]

			print(f"{idx:2x} {name}" + "".join(parts))

		print()

	def dump_growth_stats():
		print("Player Character Stat Increase Chances:")

		stat_names = "Str Skl Wpn Spd Lck Def HP".split()
		char_names = list(map(data.translate_text, data.char_names))
		char_names[6] += "*" # Gordon is hard-coded with special behavior
		name_len = max(map(len, char_names))

		parts = [f"{name:>4}" for name in stat_names]
		print(" " * (name_len + 4) + "".join(parts))

		for idx, char_stats in enumerate(data.char_growth_infos):
			name = char_names[idx]
			name += ":" + " " * (name_len - len(name))
			parts = [
				f"{x:4d}" 
				for x in (c_uint8 * sizeof(char_stats)).from_buffer(char_stats)
			]

			print(f"{idx:2x} {name}" + "".join(parts))

		print()

	def dump_metatiles(palette, text_color):
		# Create metatiles image
		mp = np.arange(0, num_metatiles, 1, np.uint8).reshape((-1, 16))
		frames, frame_times = GetAnimatedMapFrames(data, mp, True)
		SaveAnimImages(out_path.joinpath("metatiles"), None, frames, frame_times)

		# Create metatile to terrain type map image
		ys = dict(zip("cidx tbl".split(), itertools.count(8, 16)))
		xs = dict(zip(
			"ridx tidx mimg cidx".split(), 
			itertools.accumulate((8, 16, 16, -8)),
		))
		xoffs = [32 * x for x in range(16)]
		tbl_row = ys["tbl"] // 16
		tmap = np.zeros((mp.shape[0] + tbl_row, mp.shape[1] * 2 + xs["tidx"] // 16), dtype = np.uint8)
		tmap[tbl_row:, xs["mimg"] // 16::2] = mp

		mtile_terrains = data.pc_metatile_terrain_types
		frames, frame_times = GetAnimatedMapFrames(data, tmap, True)
		unique_frames = {id(frame): frame for frame in frames}
		for frame in unique_frames.values():
			draw = PIL.ImageDraw.Draw(frame)
			drawtext = functools.partial(
				draw.text,
				fill = text_color,
				font = font,
				anchor = "mm",
			)

			for i in range(16):
				drawtext((xs["cidx"] + xoffs[i], ys["cidx"]), f"{i:x}")

			for row in range(mp.shape[0]):
				drawtext((xs["ridx"], row * 16 + ys["tbl"]), f"{row:x}")

				for col in range(16):
					ttype = mtile_terrains[row * 16 + col]
					drawtext((xs["tidx"] + xoffs[col], 16 * row + ys["tbl"]), f"{ttype:x}")

		SaveAnimImages(out_path.joinpath("metatile terrains"), None, frames, frame_times)

		return
	
	def dump_terrains(map_pal, text_color):
		chr_bank = data.get_chr_bank_array(0x16)
		pal_array = data.get_palette_array(1, True)
		port_pal = ImagePalette("rgb", bytes(nes_pal[pal_array]))

		# Print terrain names and numbers
		for idx in range(num_terrains):
			dodge_chance = data.terrain_dodge_chances[idx]
			name_idx = data.terrain_name_idcs[idx]
			name = data.translate_text(data.terrain_names[name_idx])
			print(f'{idx:2x} {TerrainTypes(idx)._name_}: Name index {name_idx:x} "{name}", {dodge_chance}% to dodge')

		# Create terrain portrait images
		for idx, sprite in enumerate(data.terrain_img_metasprites):
			bitmap = np.zeros((32, 32), dtype = np.uint8)
			data.draw_sprite_type2(bitmap, chr_bank, sprite, -8, -8)

			img = Image.fromarray(bitmap, "P")
			img.putpalette(port_pal)

			save_images(out_path.joinpath("terrain portrait"), idx, img)
			save_images(
				out_path.joinpath("terrain portrait big"), 
				idx, 
				img.resize((bitmap.shape[1] * 8, bitmap.shape[0] * 8)),
			)

		# Create terrain metatiles image
		key = lambda x: x[1]
		terrain_mtiles = colls.defaultdict(list)
		mtile_it = filter(
			lambda x: np.any(data.metatile_arrays[x[0]]), 
			enumerate(data.pc_metatile_terrain_types),
		)
		for key, values in itertools.groupby(
			sorted(mtile_it, key = key),
			key = key,
		):
			terrain_mtiles[key] = [value[0] for value in values]

		terrain_mtiles[0xe] = terrain_mtiles[0x1f] = []

		xs = dict(zip(
			"tidx tname dodge midx mimg".split(),
			itertools.accumulate((8, 8, 80, 24, 16)),
		))
		max_mtiles = 14
		height = sum((max(1, (len(mtiles) + max_mtiles - 1) // max_mtiles) for mtiles in terrain_mtiles.values()))
		tmap = np.zeros((height, max_mtiles * 2 + xs["midx"] // 16), dtype = np.uint8)

		y = 0
		for tidx in range(num_terrains):
			mtiles = terrain_mtiles[tidx]
			if mtiles:
				for i in range(0, len(mtiles), max_mtiles):
					block = mtiles[i:i + max_mtiles]
					tmap[y, xs["mimg"] // 16::2][:len(block)] = block
					y += 1
			else:
				y += 1

		frames, frame_times = GetAnimatedMapFrames(data, tmap, True)
		unique_frames = {id(frame): frame for frame in frames}
		for frame in unique_frames.values():
			draw = PIL.ImageDraw.Draw(frame)
			drawtext = functools.partial(
				draw.text,
				fill = text_color,
				font = font,
				anchor = "mm",
			)

			y = 8
			for tidx in range(num_terrains):
				dodge_chance = data.terrain_dodge_chances[tidx]
				dodge_str = f"{dodge_chance}%" if dodge_chance else ""
				drawtext((xs["tidx"], y), f"{tidx:x}")
				drawtext((xs["dodge"], y), dodge_str)
				drawtext(
					(xs["tname"], y),
					" " + data.translate_text(data.terrain_names[data.terrain_name_idcs[tidx]]),
					anchor = "lm",
				)

				mtiles = terrain_mtiles[tidx]
				if mtiles:
					for i in range(0, len(mtiles), max_mtiles):
						block = mtiles[i:i + max_mtiles]
						for col, mtile_idx in enumerate(block):
							drawtext((32 * col + xs["midx"], y), f"{mtile_idx:x}")
							
						y += 16
				else:
					y += 16

		SaveAnimImages(out_path.joinpath("terrain metatiles"), None, frames, frame_times)

		# Create terrain cost image
		ys = dict(zip("uidx uname uimg tbl".split(), itertools.count(8, 16)))
		xs = dict(zip(
			"tidx mtile tname tbl".split(),
			itertools.accumulate((8, 16, 8, 72)),
		))
		tbl_row, tbl_col = (d["tbl"] // 16 for d in (ys, xs))
		terrain_mtiles = [0x30, 0, 0xa5, 0x4a, 0x4b, 0x31, 0x33, 0x50, 0x38, 0x5b, 0x39, 0x60, 0xa0, 0x6a, 0, 0x49, 0xb2, 0xa1, 0xab, 0xa9, 0xa6, 0x3b]
		mp = np.zeros((tbl_row + num_terrains, tbl_col + num_units), dtype = np.uint8)
		mp[ys["uimg"] // 16, tbl_col:] = np.arange(3, num_units * 2 + 3, 2, dtype = np.uint8)
		mp[tbl_row:, xs["mtile"] // 16] = terrain_mtiles

		frames, frame_times = GetAnimatedMapFrames(data, mp, True)
		unique_frames = {id(frame): frame for frame in frames}
		for frame in unique_frames.values():
			draw = PIL.ImageDraw.Draw(frame)
			drawtext = functools.partial(
				draw.text,
				fill = text_color,
				font = font,
				anchor = "mm",
			)

			for uidx in range(num_units):
				x = xs["tbl"] + uidx * 16
				drawtext((x, ys["uidx"]), f"{uidx:x}")
				drawtext((x, ys["uname"]), unit_abbrevs[uidx], font = font10)

			for tidx in range(num_terrains):
				y = 16 * tidx + ys["tbl"]
				drawtext((xs["tidx"], y), f"{tidx:x}")
				drawtext(
					(xs["tname"], y),
					" " + data.translate_text(data.terrain_names[data.terrain_name_idcs[tidx]]),
					anchor = "lm",
				)

				for uidx in range(num_units):
					cost = data.unit_terrain_costs[uidx][tidx]
					if cost != 0xff:
						drawtext((xs["tbl"] + uidx * 16, y), str(cost))

		SaveAnimImages(out_path.joinpath("terrain costs"), None, frames, frame_times)

		return

	def dump_items():
		tbl_infos = (
			("Mgt", data.item_mights, 3),
			("CsI", data.item_class_equip_idcs, 3, lambda x: (f"{x:3x}" if x != data.item_class_equip_none else "  -")),
			("SAI", data.item_strong_against_idcs, 3, lambda x: (f"{x:3x}" if x != data.item_strong_against_none else "  -")),
			("Wgt", data.item_weights, 3),
			("Hit", data.item_hit_chances, 3),
			("Crt", data.item_crit_chances, 3),
			("Use", data.item_uses, 3),
			("Prc", data.item_prices, 3),
			("Fx", data.item_effects, 2, lambda x: (f"{x:2x}" if x else " -")),
			("Flags", data.item_flags, 8, lambda x: get_flag_str(x, "?uxscrmi")),
			("SRq", data.item_reqs, 8, lambda x: (data.translate_text(data.char_names[(x & 0x7f) - 1]) if x & 0x80 else f"{x or '-':>3}")),
		)

		val_names = []
		vals = []
		for info in tbl_infos:
			name, tbl, width = info[:3]

			if len(info) > 3:
				fmt = info[3]
				if isinstance(fmt, str):
					fmt = fmt.format

			else:
				fmt_str = f"{{0:>{width}}}"
				fmt = lambda x: fmt_str.format(x or "-")

			val_names.append(name + " " * (width - len(name)))
			vals.append(list(map(fmt, tbl)))

		item_names = list(map(data.translate_text, data.item_names))
		max_name = max(map(len, item_names))
		padding = [" " * (max_name - len(name)) for name in item_names]

		print("Item Data:")
		print(" " * (max_name + 5) + " ".join(val_names))
		for idx, item_vals in enumerate(zip(*vals)):
			vals_str = " ".join(item_vals)
			print(f"{idx:2x} {item_names[idx]}:{padding[idx]} {vals_str}")

		print()

		# Print equippability and strong against lists
		bool_vals = ("-", "x")
		for hdr_str, addrs, tbls, item_list, list_none in (
			("Item Equippability Lists:", data.item_class_equip_tbl_addrs, data.item_class_equip_tbls, data.item_class_equip_idcs, data.item_class_equip_none),
			("Item Strong Against Lists:", data.item_strong_against_tbl_addrs, data.item_strong_against_tbls, data.item_strong_against_idcs, data.item_strong_against_none),
		):
			item_vals = colls.defaultdict(set)
			for idx, val in enumerate(item_list):
				if val != list_none:
					item_vals[val].add(idx)

			print(hdr_str)
			print(" " * 10 + " ".join(ext_unit_abbrevs))
			for idx, tbl in enumerate(tbls):
				addr = addrs[idx]
				types = [False] * (len(ext_unit_abbrevs))
				for unit_idx in tbl:
					types[unit_idx - 1] = True

				vals_str = " ".join((f"{bool_vals[x]:>2}" for x in types))

				items = item_vals[idx]
				item_name = ""
				if len(items) <= 1:
					item_name = item_names[next(iter(items))] if items else "-"

				print(f"{idx:2x} @{addr:4x}: {vals_str} {item_name}")

			print()

		# Print shop inventory lists
		print("Shop Inventory Lists:")
		for idx, tbl in enumerate(data.inv_lists):
			idcs_str = " ".join((f"{x:2x}" for x in tbl))
			names_str = ", ".join((item_names[x - 1] for x in tbl))
			print(f"{idx:2x}: {idcs_str}: {names_str}")

		print()

		return

	def dump_map_info():
		unames = list(map(data.translate_text, data.unit_names))
		uname_len = max(map(len, unames))
		pc_names = {
			idx + 1: data.translate_text(name) 
			for idx, name in enumerate(data.char_names)
		}
		npc_names = {
			idx + 1 | 0x80: data.translate_text(name) 
			for idx, name in enumerate(data.enemy_names)
		}
		name_len = max(map(len, itertools.chain(pc_names.values(), npc_names.values())))
		item_names = {
			idx + 1: data.translate_text(name)
			for idx, name in enumerate(data.item_names)
		}
		map_names = list(map(data.translate_text, data.miss_names))

		unit_tbl_fmt = (
			":idx:2x",
			"ID:e.id:2x",
			f"Name:0:{name_len}",
			f"Type:1:{uname_len}",
			"Lvl:e.level:3d",
			"HP:e.max_hp:3d",
			"XP:e.xp:3d",
			"Str:e.strength:3d",
			"Skl:e.skill:3d",
			"WLv:e.wpn_lvl:3d",
			"Spd:e.speed:3d",
			"Lck:e.luck:3d",
			"Def:e.defense:3d",
			"Mov:e.movement:3d",
			"Unk:e.unk_e:3d",
			"Res:e.resistance:3d",
			" x:e.x:2x",
			" y:e.y:2x",
			"St:e.state:2x",
			"Items:2:20",
		)
		map_unit_fmt = prepare_print_table(unit_tbl_fmt, 1, prefix = "\t")

		dlg_info_fmt = (
			":idx:2x",
			" x:e.x:2x",
			" y:e.y:2x",
			"Act:e.action:3x",
			"Dlg:e.dialog_idx:3x",
			"Mus:e.music_num:3x",
			"Til:0:3x",
			"Action Effects:1:40",
		)
		map_dlg_fmt = prepare_print_table(dlg_info_fmt, 1, prefix = "\t")

		dlg_unit_fmt = prepare_print_table(
			(":3:2x",) + unit_tbl_fmt[1:],
			1,
			prefix = "\t",
		)

		shop_info_fmt = (
			":idx:2x",
			" x:e.x:2x",
			" y:e.y:2x",
			"Type:0:10",
			"Inv:e.inv_idx:3x",
			"Til:1:3x",
		)
		map_shop_fmt = prepare_print_table(shop_info_fmt, 1, prefix = "\t")

		print("Maps:")
		for map_idx, map_info in data.maps.items():
			hdr = map_info.hdr
			map_data = map_info.data
			pre_map_info = data.get_pre_miss_info(map_idx)

			print(f"Map {map_idx:x}: {map_names[map_idx - 1]}")
			print(f"\tSize: {hdr.metatiles_wide + 1}x{hdr.metatiles_high + 1}")
			print(f"\tInitial Scroll Position: {hdr.initial_scroll_metatile_x}, {hdr.initial_scroll_metatile_y}")
			print(f"\tPre-Mission Script: {pre_map_info.dialog_idx:x}, music: {pre_map_info.music_num:x}")
			print()

			dlg_infos = data.get_miss_dlg_info(map_idx)
			used_dlg_units = set()
			if dlg_infos:
				print("\tDialog Points:")
				print_table(
					map_dlg_fmt, 
					[(info, map_data[info.y, info.x], get_dlg_action_str(pc_names, item_names, info.action)) for info in dlg_infos],
				)

				used_actions = set((info.action for info in dlg_infos))
				if used_actions.intersection((0x80, 0x81)):
					used_dlg_units.add(0)
				if 0x82 in used_actions:
					used_dlg_units.add(1)

			shop_infos = data.map_shop_lists[map_idx - 1]
			if shop_infos:
				print("\tShops:")
				print_table(
					map_shop_fmt, 
					[(info, ShopType(info.type).name, map_data[info.y, info.x]) for info in shop_infos],
				)

			for title, char_names, objs, is_pc in (
				("\tNew Player Units:", pc_names, data.map_pc_lists[map_idx], True),
				("\tEnemy Units:", npc_names, list(map(data.get_unit_obj_for_map_npc, data.map_npc_lists[map_idx])), False),
			):
				if not objs:
					continue

				num_items = 4 if is_pc else 2
				obj_items = [get_unit_items_str(item_names, num_items, obj) for obj in objs]

				print(title)
				print_table(map_unit_fmt, (
					(u, char_names[u.id], unames[u.type - 1], items) 
					for u, items in zip(objs, obj_items)
				))

			if used_dlg_units:
				unit_list = data.map_dlg_pc_lists[map_idx - 1]
				dlg_units = colls.OrderedDict()
				for idx in sorted(used_dlg_units):
					obj = unit_list[idx]
					if obj.id and obj.id <= len(pc_names) and obj.type and obj.type <= num_units:
						dlg_units[idx] = obj

				hdr, lines = format_table(dlg_unit_fmt, (
					(u, pc_names[u.id], unames[u.type - 1], get_unit_items_str(item_names, 4, u), idx) 
					for idx, u in dlg_units.items()
				))
				base_idx = next(iter(dlg_units))

				print("\tDialog Player Units:")
				print(hdr)
				for idx in used_dlg_units:
					if idx in dlg_units:
						print(lines[idx - base_idx])
					else:
						print(f"\t{idx:2x}: CORRUPT")

				print()
		return

	def dump_scripts():
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

	for hdr_str, strs in (
		("\nTerrain Names:", data.terrain_names),
		("\nEnemy Names:", data.enemy_names),
		("\nGame Strings:", data.game_strs),
	):
		print(hdr_str)
		for idx, s in enumerate(strs):
			print(f"{idx:2x}: {data.translate_text(s)}")

	print()

	for title, idcs in (
		("Pre-last Level Early Music Numbers", data.map_music_info.early_music_nums),
		("Pre-last Level Late Music Numbers", data.map_music_info.late_music_nums),
		("Last Level Music Numbers", data.last_map_music_info),
	):
		print(f"{title}: Player: {idcs[0]:2x}, Computer: {idcs[1]:2x}")

	print()

	dump_unit_types()
	dump_growth_stats()
	dump_items()
	dump_map_info()

	pal_array = data.get_nes_palette_array(0)
	remap_pal = data.get_remap_palette_array(pal_array, True)
	palette = ImagePalette("RGB", bytes(pal_array))

	experiments.run(rom, data)

	dump_scripts()

	#experiments.make_cmp_tables(all_texts.values())

	dump_metatiles(palette, 1)
	dump_terrains(palette, 1)

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