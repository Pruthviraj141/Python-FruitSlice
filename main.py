import cv2
import pygame
import random
import mediapipe as mp
import math
import time

WIDTH, HEIGHT = 1280, 720
FRUIT_SIZE = (96, 96)
SPAWN_INTERVAL = 3  # frames
MAX_FRUITS = 6

# Asset filenames - replace with your files or adjust paths
BACKGROUND_IMAGE = "background.jpg"  # full screen background
FRUIT_FILES = ["apple.png", "banana.png", "watermelon.png"]
BOMB_FILE = "bomb.png"
SOUND_SLICE = "slice.wav"
SOUND_BOMB = "explosion.wav"

# -----------------------
# Init Pygame & Mixer
# -----------------------
pygame.init()
pygame.mixer.init()
window = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Fruit Ninja with Hand Gestures - Enhanced")
clock = pygame.time.Clock()

# -----------------------
# Load Images
# -----------------------
try:
    background = pygame.image.load(BACKGROUND_IMAGE).convert()
    background = pygame.transform.scale(background, (WIDTH, HEIGHT))
except Exception as e:
    print("Warning: background image not found, using solid color.", e)
    background = None

fruit_images = []
for f in FRUIT_FILES:
    try:
        img = pygame.image.load(f).convert_alpha()
        img = pygame.transform.smoothscale(img, FRUIT_SIZE)
        fruit_images.append(img)
    except Exception as e:
        print(f"Warning: couldn't load {f}: {e}")

try:
    bomb_image = pygame.image.load(BOMB_FILE).convert_alpha()
    bomb_image = pygame.transform.smoothscale(bomb_image, FRUIT_SIZE)
except Exception as e:
    print("Warning: bomb image not found:", e)
    bomb_image = None

try:
    slice_sound = pygame.mixer.Sound(SOUND_SLICE)
except Exception:
    slice_sound = None
try:
    bomb_sound = pygame.mixer.Sound(SOUND_BOMB)
except Exception:
    bomb_sound = None

# -----------------------
# MediaPipe Hand Detection
# -----------------------
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)
mp_draw = mp.solutions.drawing_utils

# -----------------------
# Helper Classes
# -----------------------
class Piece:
    def __init__(self, image, x, y, vel_x, vel_y, rot_speed):
        self.image = image
        self.x = x
        self.y = y
        self.vel_x = vel_x
        self.vel_y = vel_y
        self.rot = 0
        self.rot_speed = rot_speed
        self.alpha = 255
        self.surface = image

    def move(self):
        self.x += self.vel_x
        self.y += self.vel_y
        self.vel_y += 0.4
        self.rot += self.rot_speed
        self.alpha = max(0, self.alpha - 2)

    def draw(self, surf):
        s = pygame.transform.rotozoom(self.surface, self.rot, 1)
        s.set_alpha(self.alpha)
        rect = s.get_rect(center=(int(self.x), int(self.y)))
        surf.blit(s, rect)

class Explosion:
    def __init__(self):
        self.start = time.time()
        self.duration = 1.0
        self.max_radius = max(WIDTH, HEIGHT)
        self.active = True

    def draw(self, surf):
        t = time.time() - self.start
        if t > self.duration:
            self.active = False
            return
        p = t / self.duration
        radius = int(self.max_radius * p)
        alpha = int(255 * (1 - p))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        col = (255, 180, 50, alpha)
        pygame.draw.circle(overlay, col, (WIDTH // 2, HEIGHT // 2), radius)
        surf.blit(overlay, (0, 0))

class Fruit:
    def __init__(self, kind="fruit"):
        self.kind = kind
        if self.kind == "bomb":
            self.image = bomb_image if bomb_image else random.choice(fruit_images)
        else:
            self.image = random.choice(fruit_images) if fruit_images else pygame.Surface(FRUIT_SIZE)
        self.x = random.randint(150, WIDTH - 150)
        self.y = HEIGHT + 80
        self.speed_x = random.uniform(-4, 4)
        self.speed_y = random.uniform(-23, -15)
        self.gravity = 0.35
        self.active = True
        self.rect_w, self.rect_h = FRUIT_SIZE
        self.left_img, self.right_img = self._slice_image(self.image)

    def _slice_image(self, image):
        w, h = image.get_size()
        left = pygame.Surface((w // 2, h), pygame.SRCALPHA)
        right = pygame.Surface((w - w // 2, h), pygame.SRCALPHA)
        left.blit(image, (0, 0), (0, 0, w // 2, h))
        right.blit(image, (0, 0), (w // 2, 0, w - w // 2, h))
        return left, right

    def move(self):
        self.x += self.speed_x
        self.y += self.speed_y
        self.speed_y += self.gravity
        if self.y > HEIGHT + 100:
            self.active = False

    def draw(self):
        window.blit(self.image, (int(self.x - self.rect_w // 2), int(self.y - self.rect_h // 2)))

    def rect(self):
        return pygame.Rect(int(self.x - self.rect_w // 2), int(self.y - self.rect_h // 2), self.rect_w, self.rect_h)

# -----------------------
# Utility Functions
# -----------------------
def check_collision(obj_rect, finger_x, finger_y):
    return obj_rect.collidepoint(finger_x, finger_y)

def spawn_item():
    if random.random() < 0.12:
        return Fruit(kind="bomb")
    else:
        return Fruit(kind="fruit")

# -----------------------
# Game State
# -----------------------
cap = cv2.VideoCapture(0)
fruits = []
pieces = []
explosions = []
spawn_timer = 0
score = 0
lives = 30
combo = 0
prev_finger_pos = None
finger_speed_threshold = 35
running = True

font = pygame.font.Font(None, 50)
small_font = pygame.font.Font(None, 30)

shake_offset = [0, 0]
shake_timer = 0

# -----------------------
# Main Loop
# -----------------------
while running:
    window.fill((0, 0, 0))
    if background:
        window.blit(background, (0, 0))
    else:
        window.fill((10, 10, 30))

    ret, frame = cap.read()
    if not ret:
        print("Camera read failed")
        break
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    finger_x = None
    finger_y = None
    slicing = False

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # Draw the landmark pattern
            mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=4),
                mp_draw.DrawingSpec(color=(255, 0, 0), thickness=2)
            )

        # Use only the first hand for slicing detection
        index_tip = results.multi_hand_landmarks[0].landmark[8]
        finger_x = int(index_tip.x * WIDTH)
        finger_y = int(index_tip.y * HEIGHT)

        if prev_finger_pos:
            dist = math.hypot(finger_x - prev_finger_pos[0], finger_y - prev_finger_pos[1])
            if dist > finger_speed_threshold:
                slicing = True

        if prev_finger_pos and finger_x is not None:
            pygame.draw.line(window, (255, 80, 80), prev_finger_pos, (finger_x, finger_y), 10)
        prev_finger_pos = (finger_x, finger_y)
    else:
        prev_finger_pos = None

    # Draw camera preview with landmarks
    cam_surface = pygame.surfarray.make_surface(cv2.transpose(frame))
    cam_surface = pygame.transform.scale(cam_surface, (320, 240))
    window.blit(cam_surface, (WIDTH - 340, 20))

    # Spawn items
    spawn_timer += 1
    if spawn_timer > SPAWN_INTERVAL and len(fruits) < MAX_FRUITS:
        fruits.append(spawn_item())
        spawn_timer = 0

    for fruit in fruits[:]:
        fruit.move()
        fruit.draw()

        if slicing and finger_x is not None and check_collision(fruit.rect(), finger_x, finger_y):
            if fruit.kind == "bomb":
                explosions.append(Explosion())
                if bomb_sound:
                    bomb_sound.play()
                score = max(0, score - 5)
                combo = 0
                shake_timer = 18
            else:
                lx = fruit.x - FRUIT_SIZE[0] // 4
                rx = fruit.x + FRUIT_SIZE[0] // 4
                ly = fruit.y
                if slice_sound:
                    slice_sound.play()
                left_piece = Piece(fruit.left_img, lx, ly, -random.uniform(2, 6), random.uniform(-14, -6), -random.uniform(2, 6))
                right_piece = Piece(fruit.right_img, rx, ly, random.uniform(2, 6), random.uniform(-14, -6), random.uniform(2, 6))
                pieces.append(left_piece)
                pieces.append(right_piece)
                score += 1
                combo += 1
            fruits.remove(fruit)

        if not fruit.active:
            if fruit.kind == "fruit":
                lives -= 1
                combo = 0
            fruits.remove(fruit)

    for p in pieces[:]:
        p.move()
        p.draw(window)
        if p.alpha <= 0 or p.y > HEIGHT + 200:
            pieces.remove(p)

    for ex in explosions[:]:
        ex.draw(window)
        if not ex.active:
            explosions.remove(ex)

    if shake_timer > 0:
        shake_timer -= 1
        shake_offset[0] = random.randint(-10, 10)
        shake_offset[1] = random.randint(-10, 10)
    else:
        shake_offset = [0, 0]

    hud = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    score_text = font.render(f"Score: {score}", True, (255, 255, 255))
    hud.blit(score_text, (10, 10))
    lives_text = small_font.render(f"Lives: {lives}", True, (255, 255, 255))
    hud.blit(lives_text, (10, 70))
    combo_text = small_font.render(f"Combo: {combo}", True, (255, 255, 255))
    hud.blit(combo_text, (10, 100))

    instr_text = small_font.render("Slice quickly with your INDEX fingertip. Avoid bombs!", True, (230, 230, 230))
    hud.blit(instr_text, (WIDTH//2 - 220, 10))

    window.blit(hud, (shake_offset[0], shake_offset[1]))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    pygame.display.update()
    clock.tick(60)

    if lives <= 0:
        print("Game Over. Final score:", score)
        running = False

cap.release()
pygame.quit()
