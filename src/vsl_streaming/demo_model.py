"""Synthetic execution fixture, not a trained sign-language recognizer."""
def build_model(num_frames=12, num_points=3, num_channels=2, num_classes=2):
    import torch
    return torch.nn.Sequential(torch.nn.Flatten(start_dim=1),
                               torch.nn.Linear(num_frames * num_points * num_channels, num_classes))
