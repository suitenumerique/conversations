import { ComponentType, SVGProps } from 'react';

import BookIcon from '@/assets/icons/uikit-custom/book-filled.svg?react';
import BookmarkIcon from '@/assets/icons/uikit-custom/bookmark-filled.svg?react';
import CarIcon from '@/assets/icons/uikit-custom/car-filled.svg?react';
import ChartIcon from '@/assets/icons/uikit-custom/chart-filled.svg?react';
import CheckmarkIcon from '@/assets/icons/uikit-custom/checkmark-filled.svg?react';
import EuroIcon from '@/assets/icons/uikit-custom/euro-filled.svg?react';
import FileIcon from '@/assets/icons/uikit-custom/file-filled.svg?react';
import FolderIcon from '@/assets/icons/uikit-custom/folder-filled.svg?react';
import GearIcon from '@/assets/icons/uikit-custom/gear-rounded-filled.svg?react';
import JusticeIcon from '@/assets/icons/uikit-custom/justice-filled.svg?react';
import KeyIcon from '@/assets/icons/uikit-custom/key-filled.svg?react';
import LaSuiteIcon from '@/assets/icons/uikit-custom/lasuite-filled.svg?react';
import MegaphoneIcon from '@/assets/icons/uikit-custom/megaphone-filled.svg?react';
import MusicIcon from '@/assets/icons/uikit-custom/music-filled.svg?react';
import PaletteIcon from '@/assets/icons/uikit-custom/palette-filled.svg?react';
import PersoIcon from '@/assets/icons/uikit-custom/perso-filled.svg?react';
import PhotoIcon from '@/assets/icons/uikit-custom/picture-filled.svg?react';
import PuzzleIcon from '@/assets/icons/uikit-custom/puzzle-filled.svg?react';
import StarIcon from '@/assets/icons/uikit-custom/star-filled.svg?react';
import TerminalIcon from '@/assets/icons/uikit-custom/terminal-filled.svg?react';

export const PROJECT_COLORS: Record<string, string> = {
  color_1: 'red-500',
  color_2: 'warning-400',
  color_3: 'orange-500',
  color_4: 'brown-350',
  color_5: 'green-650',
  color_6: 'blue-1-500',
  color_7: 'blue-2-500',
  color_8: 'pink-300',
  color_9: 'yellow-500',
  color_10: 'purple-500',
};

export const defaultIconColor = 'blue-1-500';

export const PROJECT_ICONS: Record<
  string,
  ComponentType<SVGProps<SVGSVGElement>>
> = {
  folder: FolderIcon,
  file: FileIcon,
  perso: PersoIcon,
  gear: GearIcon,
  megaphone: MegaphoneIcon,
  star: StarIcon,
  bookmark: BookmarkIcon,
  chart: ChartIcon,
  photo: PhotoIcon,
  euro: EuroIcon,
  key: KeyIcon,
  justice: JusticeIcon,
  book: BookIcon,
  puzzle: PuzzleIcon,
  palette: PaletteIcon,
  terminal: TerminalIcon,
  car: CarIcon,
  music: MusicIcon,
  checkmark: CheckmarkIcon,
  la_suite: LaSuiteIcon,
};
