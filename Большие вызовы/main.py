from PIL import Image
import os
from models import load_model


def save_image(image: Image.Image, path: str):
    if os.path.isdir(path):
        path = os.path.join(path, 'generated.png')
    elif not path.endswith('.png'):
        path += '.png'
    print("saving image to", path)
    image.save(path)
    return image


model = load_model()

image = model.generate_image(
    text='',  # 'Pistachio Pudding'
    seed=-1,
    grid_size=1,
    is_seamless=True
    # top_k=50
    # is_seamless=False,
    # temperature=1,
    # supercondition_factor=8,
    # is_verbose=False
)

save_image(image, 'image.png')