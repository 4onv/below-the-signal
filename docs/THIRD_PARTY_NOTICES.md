# Third-party notices

BELOW THE SIGNAL's MIT License applies to the game's original source code and authored procedural assets. The components below retain their upstream copyright notices and licenses.

## pygame-ce 2.5.6

The installed package's `pygame_ce-2.5.6.dist-info/METADATA` identifies pygame-ce as **LGPL-2.1-or-later**. Its installed license text is copied unchanged to [licenses/pygame-ce/LGPL.txt](licenses/pygame-ce/LGPL.txt).

- Project and source: [pygame-community/pygame-ce, tag 2.5.6](https://github.com/pygame-community/pygame-ce/tree/2.5.6).
- Upstream license: [docs/LGPL.txt](https://github.com/pygame-community/pygame-ce/blob/2.5.6/docs/LGPL.txt).
- Dependency notices: [docs/licenses at tag 2.5.6](https://github.com/pygame-community/pygame-ce/tree/2.5.6/docs/licenses).

The complete 20-file upstream dependency-notice directory has been retained in [licenses/pygame-ce](licenses/pygame-ce). It covers FLAC, FluidSynth, FreeType, JPEG, ModPlug, mpg123, NumPy, Ogg/Vorbis, Opus, opusfile, PNG, PortMidi, SDL2, SDL2_image, SDL2_mixer, SDL_gfx, sse2neon, TIFF, WebP, and zlib. This preserves upstream's notice collection; it does not mean the game imports or uses every component in that collection.

The installed Windows wheel includes SDL2, SDL2_image, SDL2_mixer, SDL2_ttf, FreeType, JPEG, Ogg, Opus, opusfile, PNG, TIFF, WavPack, WebP, libxmp, and PortMidi shared libraries. The game's own audio synthesis uses Python code and pygame's mixer.

Additional notices were retrieved from the libraries' own repositories for the versions identified in the installed Windows DLLs:

| Component | Version evidence | Preserved notices and upstream source |
| --- | --- | --- |
| SDL_ttf 2.24.0 | Windows DLL version resource | [License](licenses/pygame-ce/LICENSE.sdl2_ttf.txt), copied from [release-2.24.0/LICENSE.txt](https://github.com/libsdl-org/SDL_ttf/blob/release-2.24.0/LICENSE.txt) |
| WavPack 5.6.0 | Windows DLL version resource | [License](licenses/pygame-ce/LICENSE.wavpack.txt) and [COPYING](licenses/pygame-ce/COPYING.wavpack.txt), copied from [tag 5.6.0](https://github.com/dbry/WavPack/tree/5.6.0) |
| libxmp 4.6.1 | DLL's exported `xmp_version` value | [COPYING](licenses/pygame-ce/COPYING.libxmp.txt), [README](licenses/pygame-ce/README.libxmp.txt), and [ProWizard notice](licenses/pygame-ce/LICENSE.libxmp-prowizard.txt), copied from [tag libxmp-4.6.1](https://github.com/libxmp/libxmp/tree/libxmp-4.6.1) |

## Bundled interface font

The interface uses `pygame.font.Font(None, ...)`, which selects pygame-ce's bundled `freesansbold.ttf`. Its embedded metadata identifies the font as **FreeSans**, carries the notice **Copyright 2002 Free Software Foundation**, and states that its use is subject to the GNU General Public License. The metadata links to [GNU's GPL page](https://www.gnu.org/copyleft/gpl.html) without specifying a license version.

The extracted font attribution is preserved in [licenses/pygame-ce/FONT_NOTICE.txt](licenses/pygame-ce/FONT_NOTICE.txt). This bundled font is a third-party asset and is not covered by the game's MIT License.

GNU FreeFont's [current official license page](https://www.gnu.org/software/freefont/license.html) publishes GPL version 3-or-later terms with a font-embedding exception. An [unchanged copy of that page](licenses/pygame-ce/FREEFONT-UPSTREAM-LICENSE.html), the [GPL version 2 text](licenses/pygame-ce/GPL-2.0.txt), and the [GPL version 3 text](licenses/pygame-ce/GPL-3.0.txt) are retained here. The GPL texts were downloaded from [GNU's version 2 page](https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt) and [version 3 page](https://www.gnu.org/licenses/gpl-3.0.txt).

The bundled font identifies itself as revision 0.4 with a 2002 copyright notice. Its metadata contains neither a GPL version nor the font exception; this inventory records the historical file and the current upstream page separately and does not attribute an unverified version-specific exception to the bundled file. The distributed font can also be found in [pygame-ce 2.5.6's source tree](https://github.com/pygame-community/pygame-ce/blob/2.5.6/src_py/freesansbold.ttf).

## Python runtime and standard library

The release build environment uses **CPython 3.12.14**. The runtime's `LICENSE.txt` identifies the Python Software Foundation License Version 2 and includes the additional historical and incorporated-software notices. Windows distributions include a copy of that complete runtime license alongside the application.

- Project: [Python](https://www.python.org/).
- License documentation: [Python 3.12 history and license](https://docs.python.org/3.12/license.html).

Python and pygame-ce have not been modified as part of this game.
