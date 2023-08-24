# -*- coding: utf-8 -*-
import logging
import re
import random

try:
    import pyffish as sf
except ImportError:
    print("No pyffish module installed!")

from const import CATEGORIES

WHITE, BLACK = False, True
FILES = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

STANDARD_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

log = logging.getLogger(__name__)


def file_of(piece: str, rank: str) -> int:
    """
    Returns the 0-based file of the specified piece in the rank.
    Returns -1 if the piece is not in the rank.
    """
    pos = rank.find(piece)
    if pos >= 0:
        return sum(int(p) if p.isdigit() else 1 for p in rank[:pos])
    else:
        return -1


def modded_variant(variant: str, chess960: bool, initial_fen: str) -> str:
    """Some variants need to be treated differently by pyffish."""
    return variant


class FairyBoard:
    def __init__(
        self, variant: str, initial_fen="", chess960=False, count_started=0, disabled_fen=""
    ):
        self.variant = modded_variant(variant, chess960, initial_fen)
        self.chess960 = chess960
        self.sfen = False
        self.show_promoted = False
        self.nnue = initial_fen == ""
        self.initial_fen = (
            initial_fen if initial_fen else self.start_fen(variant, chess960, disabled_fen)
        )
        self.move_stack: list[str] = []
        self.ply = 0
        self.color = WHITE if self.initial_fen.split()[1] == "w" else BLACK
        self.fen = self.initial_fen
        self.manual_count = count_started != 0
        self.count_started = count_started
        self.notation = sf.NOTATION_XIANGQI_WXF

    def start_fen(self, variant, chess960=False, disabled_fen=""):
        return sf.start_fen(variant)

    @property
    def initial_sfen(self):
        return sf.get_fen(self.variant, self.initial_fen, [], False, True)

    def push(self, move):
        try:
            self.move_stack.append(move)
            self.ply += 1
            self.color = not self.color
            self.fen = sf.get_fen(
                self.variant,
                self.fen,
                [move],
                self.chess960,
                self.sfen,
                self.show_promoted,
                self.count_started,
            )
        except Exception:
            self.pop()
            log.error(
                "ERROR: sf.get_fen() failed on %s %s %s",
                self.initial_fen,
                ",".join(self.move_stack),
                self.chess960,
            )
            raise

    def pop(self):
        self.move_stack.pop()
        self.ply -= 1
        self.color = not self.color
        self.fen = sf.get_fen(
            self.variant,
            self.initial_fen,
            self.move_stack,
            self.chess960,
            self.sfen,
            self.show_promoted,
            self.count_started,
        )

    def get_san(self, move):
        return sf.get_san(self.variant, self.fen, move, self.chess960, self.notation)

    def legal_moves(self):
        # move legality can depend on history, e.g., passing and bikjang
        return sf.legal_moves(self.variant, self.initial_fen, self.move_stack, self.chess960)

    def is_checked(self):
        return sf.gives_check(self.variant, self.fen, [], self.chess960)

    def insufficient_material(self):
        return sf.has_insufficient_material(self.variant, self.fen, [], self.chess960)

    def is_immediate_game_end(self):
        immediate_end, result = sf.is_immediate_game_end(
            self.variant, self.initial_fen, self.move_stack, self.chess960
        )
        return immediate_end, result

    def is_optional_game_end(self):
        return sf.is_optional_game_end(
            self.variant,
            self.initial_fen,
            self.move_stack,
            self.chess960,
            self.count_started,
        )

    def is_claimable_draw(self):
        optional_end, result = self.is_optional_game_end()
        return optional_end and result == 0

    def game_result(self):
        return sf.game_result(self.variant, self.initial_fen, self.move_stack, self.chess960)

    def print_pos(self):
        print()
        uni_pieces = {
            "R": "♜",
            "N": "♞",
            "B": "♝",
            "Q": "♛",
            "K": "♚",
            "P": "♟",
            "r": "♖",
            "n": "♘",
            "b": "♗",
            "q": "♕",
            "k": "♔",
            "p": "♙",
            ".": "·",
            "/": "\n",
        }
        fen = self.fen
        if "[" in fen:
            board, rest = fen.split("[")
        else:
            board = fen.split()[0]
        board = board.replace("+", "")
        board = re.sub(r"\d", (lambda m: "." * int(m.group(0))), board)
        print("", " ".join(uni_pieces.get(p, p) for p in board))

    def janggi_setup(self, color):
        if color == "b":
            left = random.choice(("nb", "bn"))
            right = random.choice(("nb", "bn"))
            fen = "r%sa1a%sr/4k4/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/4K4/RNBA1ABNR w - - 0 1" % (
                left,
                right,
            )
        else:
            left = random.choice(("NB", "BN"))
            right = random.choice(("NB", "BN"))
            parts = self.initial_fen.split("/")
            parts[-1] = "R%sA1A%sR w - - 0 1" % (left, right)
            fen = "/".join(parts)
        print("-------new FEN", fen)
        self.initial_fen = fen
        self.fen = self.initial_fen

    def shuffle_start(self):
        """Create random initial position.
        The king is placed somewhere between the two rooks.
        The bishops are placed on opposite-colored squares.
        Same for queen and archbishop in caparandom."""

        castl = ""
        capa = self.variant in ("capablanca", "capahouse")
        seirawan = self.variant in ("seirawan", "shouse")

        # https://www.chessvariants.com/contests/10/crc.html
        # we don't skip spositions that have unprotected pawns
        if capa:
            board = [""] * 10
            positions = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            bright = [1, 3, 5, 7, 9]
            dark = [0, 2, 4, 6, 8]

            # 1. select queen or the archbishop to be placed first
            piece = random.choice("qa")

            # 2. place the selected 1st piece upon a bright square
            piece_pos = random.choice(bright)
            board[piece_pos] = piece
            positions.remove(piece_pos)
            bright.remove(piece_pos)

            # 3. place the selected 2nd piece upon a dark square
            piece_pos = random.choice(dark)
            board[piece_pos] = "q" if piece == "a" else "a"
            positions.remove(piece_pos)
            dark.remove(piece_pos)
        else:
            board = [""] * 8
            positions = [0, 1, 2, 3, 4, 5, 6, 7]
            bright = [1, 3, 5, 7]
            dark = [0, 2, 4, 6]

        # 4. one bishop has to be placed upon a bright square
        piece_pos = random.choice(bright)
        board[piece_pos] = "b"
        positions.remove(piece_pos)
        if seirawan:
            castl += FILES[piece_pos]

        # 5. one bishop has to be placed upon a dark square
        piece_pos = random.choice(dark)
        board[piece_pos] = "b"
        positions.remove(piece_pos)
        if seirawan:
            castl += FILES[piece_pos]

        if capa:
            # 6. one chancellor has to be placed upon a free square
            piece_pos = random.choice(positions)
            board[piece_pos] = "c"
            positions.remove(piece_pos)
        else:
            piece_pos = random.choice(positions)
            board[piece_pos] = "q"
            positions.remove(piece_pos)
            if seirawan:
                castl += FILES[piece_pos]

        # 7. one knight has to be placed upon a free square
        piece_pos = random.choice(positions)
        board[piece_pos] = "n"
        positions.remove(piece_pos)
        if seirawan:
            castl += FILES[piece_pos]

        # 8. one knight has to be placed upon a free square
        piece_pos = random.choice(positions)
        board[piece_pos] = "n"
        positions.remove(piece_pos)
        if seirawan:
            castl += FILES[piece_pos]

        # 9. set the king upon the center of three free squares left
        piece_pos = positions[1]
        board[piece_pos] = "k"

        # 10. set the rooks upon the both last free squares left
        piece_pos = positions[0]
        board[piece_pos] = "r"
        castl += "q" if seirawan else FILES[piece_pos]

        piece_pos = positions[2]
        board[piece_pos] = "r"
        castl += "k" if seirawan else FILES[piece_pos]

        fen = "".join(board)
        if capa:
            body = "/pppppppppp/10/10/10/10/PPPPPPPPPP/"
        else:
            body = "/pppppppp/8/8/8/8/PPPPPPPP/"

        if self.variant in ("crazyhouse", "capahouse"):
            holdings = "[]"
        elif seirawan:
            holdings = "[HEhe]"
        else:
            holdings = ""

        checks = "3+3 " if self.variant == "3check" else ""

        fen = (
            fen
            + body
            + fen.upper()
            + holdings
            + " w "
            + castl.upper()
            + castl
            + " - "
            + checks
            + "0 1"
        )
        return fen


if __name__ == "__main__":
    sf.set_option("VariantPath", "variants.ini")
    print(sf.version())
    print(sf.info())
    print(sf.variants())
