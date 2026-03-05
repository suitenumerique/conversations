import { ComponentType, SVGProps } from 'react';

import BookIcon from '@/assets/icons/uikit-custom/book-filled.svg';
import BookmarkIcon from '@/assets/icons/uikit-custom/bookmark-filled.svg';
import CarIcon from '@/assets/icons/uikit-custom/car-filled.svg';
import ChartIcon from '@/assets/icons/uikit-custom/chart-filled.svg';
import CheckmarkIcon from '@/assets/icons/uikit-custom/checkmark-filled.svg';
import EuroIcon from '@/assets/icons/uikit-custom/euro-filled.svg';
import FileIcon from '@/assets/icons/uikit-custom/file-filled.svg';
import FolderIcon from '@/assets/icons/uikit-custom/folder-filled.svg';
import GearIcon from '@/assets/icons/uikit-custom/gear-rounded-filled.svg';
import JusticeIcon from '@/assets/icons/uikit-custom/justice-filled.svg';
import KeyIcon from '@/assets/icons/uikit-custom/key-filled.svg';
import LaSuiteIcon from '@/assets/icons/uikit-custom/lasuite-filled.svg';
import MegaphoneIcon from '@/assets/icons/uikit-custom/megaphone-filled.svg';
import MusicIcon from '@/assets/icons/uikit-custom/music-filled.svg';
import PaletteIcon from '@/assets/icons/uikit-custom/palette-filled.svg';
import PersoIcon from '@/assets/icons/uikit-custom/perso-filled.svg';
import PhotoIcon from '@/assets/icons/uikit-custom/picture-filled.svg';
import PuzzleIcon from '@/assets/icons/uikit-custom/puzzle-filled.svg';
import StarIcon from '@/assets/icons/uikit-custom/star-filled.svg';
import TerminalIcon from '@/assets/icons/uikit-custom/terminal-filled.svg';

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
