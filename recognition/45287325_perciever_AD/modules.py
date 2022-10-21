import torch
import torch.nn as nn

def Conv1D(out_dim):
    return nn.Linear(out_dim, out_dim)

class CrossAttention(nn.Module):
    """
    The inputs are a latent array and the actual data. The latent array is the query and the data forms the key and value.

    First process inputs through a batch normalisation, before putting them through a linear layer.

    Then put them through the attention block, before one last linear layer
    """
    def __init__(self, d_latents):
        super(CrossAttention, self).__init__()
        self.attn = nn.MultiheadAttention(d_latents, 4, batch_first=True)           
        self.o_l = nn.Linear(d_latents, d_latents)

    def forward(self, latent, kv):
        attn = self.attn(latent, kv, kv)[0]
        output = self.o_l(attn)
        return output

class SelfAttention(nn.Module):
    """
    The inputs are a latent array, which is the query, key and value. 

    First process inputs through a batch normalisation, before putting them through a linear layer.

    Then put them through the attention block, before one last linear layer
    """
    def __init__(self, d_latents):
        super(SelfAttention, self).__init__()
        self.attn = nn.MultiheadAttention(d_latents, 1, batch_first=True)           
        self.o_l = nn.Linear(d_latents, d_latents)

    def forward(self, latent):
        attn = self.attn(latent, latent, latent)[0]
        output = self.o_l(attn)
        return output


class LatentTransformer(nn.Module):
    """
    Consists of a self attention block between two linear layers. 
    """
    def __init__(self, d_latents, depth) -> None:
        super(LatentTransformer, self).__init__()
        self.ff = nn.ModuleList([MLP(d_latents) for _ in range(depth)])
        self.sa = nn.ModuleList([SelfAttention(d_latents) for _ in range(depth)])
        self.depth = depth
        self.ln1 = nn.LayerNorm(d_latents)
        self.ln2 = nn.LayerNorm(d_latents)

    def forward(self, x):
        latent = x
        for i in range(self.depth):
            latent = self.sa[i](self.ln1(latent)) + latent
            latent = self.ff[i](self.ln2(latent)) + latent
        return latent

class MLP(nn.Module):
    """
    Consists of a layer normalisation, followed by a linear layer with GeLU activation before another linear layer. 
    """
    def __init__(self, d_latents) -> None:
        super(MLP, self).__init__()
        self.ln = nn.LayerNorm(d_latents)
        self.l1 = nn.Linear(d_latents, d_latents)
        self.l2 = nn.Linear(d_latents, d_latents)
        self.gelu = nn.GELU()

    def forward(self, x):
        x = self.ln(x)
        x = self.l1(x)
        x = self.gelu(x)
        x = self.l2(x)
        return x

class Block(nn.Module):
    """
    A Cross attend block followed.
    """
    def __init__(self, d_latents) -> None:
        super(Block, self).__init__()
        self.ca = CrossAttention(d_latents)
        self.ff = MLP(d_latents)
        self.ln1 = nn.LayerNorm(d_latents)
        self.ln2 = nn.LayerNorm(d_latents)

    def forward(self, x, data):
        attn = self.ca(self.ln1(x), data)
        x = attn + x
        x = self.ff(self.ln2(x) + x)
        return x
        

class Output(nn.Module):
    # FIX PARAMTERER HERE
    def __init__(self, n_latents, n_classes=2) -> None:
        super(Output, self).__init__()
        self.project = nn.Linear(n_latents, n_classes)
    
    def forward(self, x):
        average = torch.mean(x, dim=2)
        logits = self.project(average)
        return logits


class Perciever(nn.Module):
    def __init__(self, n_latents, d_latents, transformer_depth, n_cross_attends) -> None:
        super(Perciever, self).__init__()
        self.depth = n_cross_attends

        # Initialise the latent array
        latent = torch.empty(n_latents, d_latents)
        nn.init.trunc_normal_(latent,std=0.02)
        self.latent=nn.Parameter(latent)

        self.ca = nn.ModuleList([Block(d_latents) for _ in range(n_cross_attends)])
        self.lt = nn.ModuleList([LatentTransformer(d_latents, transformer_depth) for _ in range(n_cross_attends)])
        self.op = Output(n_latents)

        self.image_project = nn.Linear(1, d_latents)

        self.pe = nn.Parameter(torch.empty(1, 240*240, d_latents))
        nn.init.normal_(self.pe)


    def forward(self, data):
        b, _, _, _ = data.size()
        flat_img = torch.flatten(data, start_dim=1)[:, :, None]
        proj_img = self.image_project(flat_img)

        proj_img = proj_img + self.pe.repeat(b, 1, 1)

        x = self.latent.repeat(b, 1, 1)

        for i in range(self.depth):
            x = self.ca[i](x, proj_img)
            x = self.lt[i](x)
        output = self.op(x)
        return output
