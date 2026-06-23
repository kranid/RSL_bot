import enum

class FileType(str, enum.Enum):
    image       = 'image'
    grid_image  = 'grid_image'
    emoji       = 'emoji'
    video       = 'video'
    model_3d    = 'model_3d'
    document    = 'document'
    intermediate_state = 'intermediate_state'
    audio       = 'audio'
