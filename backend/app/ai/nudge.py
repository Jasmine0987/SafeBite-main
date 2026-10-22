from pathlib import Path
import torch
import torch.nn as nn

WEIGHTS = Path(__file__).parent / "weights" / "bilstm_nudge.pt"
SEQ_LEN = 10
_model = None

class BiLSTMNudge(nn.Module):
    def __init__(self, input_dim=3, hidden=16):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, batch_first=True, bidirectional=True)
        self.fc = nn.Linear(hidden * 2, 1)
    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.fc(out[:, -1, :]))

def nudge_risk(scans):
    global _model
    if not WEIGHTS.exists():
        return None
    if _model is None:
        _model = BiLSTMNudge()
        _model.load_state_dict(torch.load(WEIGHTS, map_location="cpu"))
        _model.eval()
    seq = scans[-SEQ_LEN:]
    seq = [[0.0, 0.0, 0.0]] * (SEQ_LEN - len(seq)) + seq
    x = torch.tensor([seq], dtype=torch.float32)
    with torch.no_grad():
        return float(_model(x).item())
