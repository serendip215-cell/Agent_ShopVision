# -*- coding: utf-8 -*-
"""Single-GPU stand-in for ``DistributedDataParallel``.

On this WSL2 + RTX 5060 Ti setup every NCCL collective (``all_reduce``,
``all_gather``) hangs forever, so single-GPU training cannot use DDP at all.

``NoDDP`` keeps the two things the rest of the training code relies on:

* ``model.module``            - ``train.py`` uses ``model.module`` directly.
* ``"module."`` key prefixing - registering the wrapped model as the ``module``
  submodule makes ``nn.Module.state_dict()`` / ``load_state_dict()`` produce and
  accept exactly the same key names a DDP wrapper would, so checkpoints stay
  compatible with the official DDP-saved weights and with
  ``cn_clip/eval/extract_features.py``.
"""

from contextlib import nullcontext

import torch


class NoDDP(torch.nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, *args, **kwargs):
        return self.module(*args, **kwargs)

    # DDP API used by the training / evaluation loop.
    def no_sync(self):
        return nullcontext()

    def _set_static_graph(self):
        return None

    def __getattr__(self, name):
        # Fall back to the wrapped module for anything not defined here
        # (e.g. ``model.visual``, ``model.logit_scale``).
        try:
            return super().__getattr__(name)
        except AttributeError:
            if name == "module":
                raise
            return getattr(self.module, name)
