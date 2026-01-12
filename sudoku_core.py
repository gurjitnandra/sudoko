import random
from typing import List, Optional, Tuple


class Sudoku:
    BOARD_SIZE = 9
    DIFFICULTY_MAP = {
        "easy": 36,
        "medium": 45,
        "hard": 54,
    }

    def __init__(self, difficulty: str = "easy"):
        self.set_difficulty(difficulty)
        self._generate_new_game()

    def set_difficulty(self, difficulty: str) -> None:
        difficulty = difficulty.lower()
        if difficulty not in self.DIFFICULTY_MAP:
            difficulty = "easy"
        self.difficulty = difficulty

    def _generate_new_game(self) -> None:
        self.solution = [[0] * self.BOARD_SIZE for _ in range(self.BOARD_SIZE)]
        self._fill_solution(self.solution)

        puzzle = [row[:] for row in self.solution]
        self._remove_values(puzzle)

        self.puzzle = puzzle
        self.state = [row[:] for row in puzzle]
        self.givens = [[cell != 0 for cell in row] for row in puzzle]

    def reset(self, difficulty: Optional[str] = None) -> None:
        if difficulty:
            self.set_difficulty(difficulty)
        self._generate_new_game()

    def get_state(self) -> List[List[int]]:
        return [row[:] for row in self.state]

    def get_puzzle(self) -> List[List[int]]:
        return [row[:] for row in self.puzzle]

    def get_givens(self) -> List[List[bool]]:
        return [row[:] for row in self.givens]

    def _fill_solution(self, board: List[List[int]]) -> bool:
        empty_cell = self._find_empty(board)
        if not empty_cell:
            return True
        row, col = empty_cell

        numbers = list(range(1, 10))
        random.shuffle(numbers)

        for num in numbers:
            if self._is_valid(board, num, row, col):
                board[row][col] = num
                if self._fill_solution(board):
                    return True
                board[row][col] = 0

        return False

    @staticmethod
    def _find_empty(board: List[List[int]]) -> Optional[Tuple[int, int]]:
        for i in range(Sudoku.BOARD_SIZE):
            for j in range(Sudoku.BOARD_SIZE):
                if board[i][j] == 0:
                    return i, j
        return None

    @staticmethod
    def _is_valid(board: List[List[int]], num: int, row: int, col: int) -> bool:
        if any(board[row][i] == num for i in range(Sudoku.BOARD_SIZE)):
            return False
        if any(board[i][col] == num for i in range(Sudoku.BOARD_SIZE)):
            return False

        start_row, start_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(start_row, start_row + 3):
            for j in range(start_col, start_col + 3):
                if board[i][j] == num:
                    return False
        return True

    def _remove_values(self, board: List[List[int]]) -> None:
        to_remove = self.DIFFICULTY_MAP.get(self.difficulty, 36)
        removed = 0
        attempts = 0
        max_attempts = to_remove * 5

        while removed < to_remove and attempts < max_attempts:
            row = random.randrange(self.BOARD_SIZE)
            col = random.randrange(self.BOARD_SIZE)
            if board[row][col] != 0:
                board[row][col] = 0
                removed += 1
            attempts += 1

    def is_given(self, row: int, col: int) -> bool:
        return self.givens[row][col]

    def get_solution_value(self, row: int, col: int) -> int:
        return self.solution[row][col]

    def set_value(self, row: int, col: int, value: int) -> bool:
        if self.givens[row][col]:
            return False

        if value == 0:
            self.state[row][col] = 0
            return True

        if not (1 <= value <= 9):
            return False

        if self.solution[row][col] == value:
            self.state[row][col] = value
            return True

        return False

    def is_complete(self) -> bool:
        return self.state == self.solution

    def to_dict(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "board": self.get_state(),
            "givens": self.get_givens(),
            "complete": self.is_complete(),
        }

