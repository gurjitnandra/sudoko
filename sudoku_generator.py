import random
import sys
from dataclasses import dataclass

import pygame


class Sudoku:
    def __init__(self, difficulty: str = 'easy'):
        self.difficulty = difficulty.lower()
        if self.difficulty not in {'easy', 'medium', 'hard'}:
            self.difficulty = 'easy'

        self.solution = [[0] * 9 for _ in range(9)]
        self._fill_solution(self.solution)

        self.board = [row[:] for row in self.solution]
        self.remove_values()

    def _fill_solution(self, board):
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
    def _find_empty(board):
        for i in range(9):
            for j in range(9):
                if board[i][j] == 0:
                    return i, j
        return None

    @staticmethod
    def _is_valid(board, num, row, col):
        if any(board[row][i] == num for i in range(9)):
            return False
        if any(board[i][col] == num for i in range(9)):
            return False

        start_row, start_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(start_row, start_row + 3):
            for j in range(start_col, start_col + 3):
                if board[i][j] == num:
                    return False

        return True

    def remove_values(self):
        remove_map = {
            'easy': 36,
            'medium': 45,
            'hard': 54,
        }
        to_remove = remove_map.get(self.difficulty, 36)

        removed = 0
        attempts = 0
        max_attempts = 200
        while removed < to_remove and attempts < max_attempts:
            row = random.randrange(9)
            col = random.randrange(9)
            if self.board[row][col] != 0:
                self.board[row][col] = 0
                removed += 1
            attempts += 1

    def is_correct_value(self, row, col, value):
        return self.solution[row][col] == value


@dataclass
class Cell:
    value: int
    editable: bool


class SudokuGame:
    FONT_NAME = 'arial'

    BG_COLOR = (0, 0, 0)
    GRID_COLOR = (80, 80, 80)
    SUBGRID_COLOR = (200, 200, 200)
    SELECTED_COLOR = (255, 200, 0)
    GIVEN_COLOR = (230, 230, 230)
    EDITABLE_COLOR = (120, 200, 120)
    TEXT_COLOR = (220, 220, 220)

    def __init__(self, sudoku: Sudoku, cell_size: int = 60):
        self.cell_size = max(30, min(cell_size, 120))
        self.board_size = self.cell_size * 9
        self.info_height = max(100, int(self.cell_size * 1.8))
        self.window_size = (self.board_size, self.board_size + self.info_height)

        pygame.init()
        pygame.display.set_caption('Sudoku')
        self.screen = pygame.display.set_mode(self.window_size)
        self.clock = pygame.time.Clock()

        font_size = max(28, int(self.cell_size * 0.6))
        info_font_size = max(18, int(self.cell_size * 0.35))
        self.font = pygame.font.SysFont(self.FONT_NAME, font_size)
        self.info_font = pygame.font.SysFont(self.FONT_NAME, info_font_size)

        self.sudoku = sudoku
        self.cells = [
            [Cell(value=num, editable=(num == 0)) for num in row]
            for row in self.sudoku.board
        ]

        self.selected = (0, 0)
        self.message = 'Use mouse or arrow keys to select a cell.'
        self.running = True

    def run(self):
        while self.running:
            self.clock.tick(60)
            self._handle_events()
            self._draw()
            pygame.display.flip()

        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._select_cell(event.pos)
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)

    def _select_cell(self, pos):
        x, y = pos
        if x < self.board_size and y < self.board_size:
            col = x // self.cell_size
            row = y // self.cell_size
            self.selected = (row, col)

    def _handle_key(self, key):
        row, col = self.selected
        if key in (pygame.K_RIGHT, pygame.K_d):
            self.selected = (row, (col + 1) % 9)
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.selected = (row, (col - 1) % 9)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.selected = ((row + 1) % 9, col)
        elif key in (pygame.K_UP, pygame.K_w):
            self.selected = ((row - 1) % 9, col)
        elif key in (pygame.K_BACKSPACE, pygame.K_DELETE, pygame.K_0, pygame.K_KP0):
            self._update_cell(0)
        elif pygame.K_1 <= key <= pygame.K_9:
            self._update_cell(key - pygame.K_0)
        elif pygame.K_KP1 <= key <= pygame.K_KP9:
            self._update_cell(key - pygame.K_KP0)

    def _update_cell(self, value):
        row, col = self.selected
        cell = self.cells[row][col]
        if not cell.editable:
            self.message = 'Cannot change a given number.'
            return

        if value == 0:
            cell.value = 0
            self.message = 'Cell cleared.'
            return

        if self.sudoku.is_correct_value(row, col, value):
            cell.value = value
            self.message = 'Good move!'
            if self._is_completed():
                self.message = 'Puzzle solved! Press Esc to exit.'
        else:
            self.message = 'Incorrect value. Try again.'

    def _is_completed(self):
        for i in range(9):
            for j in range(9):
                if self.cells[i][j].value != self.sudoku.solution[i][j]:
                    return False
        return True

    def _draw(self):
        self.screen.fill(self.BG_COLOR)
        self._draw_grid()
        self._draw_numbers()
        self._draw_message()

    def _draw_grid(self):
        for i in range(10):
            line_width = 4 if i % 3 == 0 else 1
            color = self.SUBGRID_COLOR if i % 3 == 0 else self.GRID_COLOR
            pygame.draw.line(
                self.screen,
                color,
                (0, i * self.cell_size),
                (self.board_size, i * self.cell_size),
                line_width,
            )
            pygame.draw.line(
                self.screen,
                color,
                (i * self.cell_size, 0),
                (i * self.cell_size, self.board_size),
                line_width,
            )

        row, col = self.selected
        pygame.draw.rect(
            self.screen,
            self.SELECTED_COLOR,
            (
                col * self.cell_size,
                row * self.cell_size,
                self.cell_size,
                self.cell_size,
            ),
            4,
        )

    def _draw_numbers(self):
        for i in range(9):
            for j in range(9):
                value = self.cells[i][j].value
                if value == 0:
                    continue

                if self.cells[i][j].editable:
                    color = self.EDITABLE_COLOR
                else:
                    color = self.GIVEN_COLOR

                text_surface = self.font.render(str(value), True, color)
                text_rect = text_surface.get_rect(center=(
                    j * self.cell_size + self.cell_size // 2,
                    i * self.cell_size + self.cell_size // 2,
                ))
                self.screen.blit(text_surface, text_rect)

    def _draw_message(self):
        message_surface = self.info_font.render(self.message, True, self.TEXT_COLOR)
        self.screen.blit(message_surface, (10, self.board_size + 20))

        controls = 'Controls: Arrow/WASD = move | 1-9 = set | 0/Backspace = clear | Esc = quit'
        controls_surface = self.info_font.render(controls, True, self.TEXT_COLOR)
        self.screen.blit(controls_surface, (10, self.board_size + 60))


def main():
    difficulty = input('Choose difficulty (easy, medium, hard): ').strip().lower()
    sudoku = Sudoku(difficulty)

    size_input = input('Enter cell size in pixels (30-120, default 60): ').strip()
    try:
        cell_size = int(size_input) if size_input else 60
    except ValueError:
        cell_size = 60

    game = SudokuGame(sudoku, cell_size)
    game.run()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit()
