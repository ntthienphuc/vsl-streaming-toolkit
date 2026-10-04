"""Replace this fixture with YOUR trained architecture.

Export using --factory examples.user_model:build_model. Input must match the
profile; return one float32 raw-logit tensor [B,num_classes].
"""
def build_model(num_frames=60, num_points=49, num_channels=2, num_classes=2):
    import torch
    return torch.nn.Sequential(torch.nn.Flatten(start_dim=1),
                               torch.nn.Linear(num_frames * num_points * num_channels, num_classes))
