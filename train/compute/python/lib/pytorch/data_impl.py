import copy
import random
from typing import Dict, Set, List, Any, Callable

import torch

from ..data import DataGenerator, register_data_generator
from ..init_helper import get_logger

logger = get_logger()

pytorch_dtype_map: Dict[str, torch.dtype] = {
    "float": torch.float32,
    "double": torch.float64,
    "int": torch.int32,
    "long": torch.int64,
}


def materialize_arg(arg: Dict[str, Any], device: str) -> Any:
    """
    Given an arg configuration, materialize the test data for that arg.
    """

    def create_tensor(attr: Dict[str, Any]):
        shape = attr["shape"]
        if len(shape) > 0:
            if attr["dtype"] == "float" or attr["dtype"] == "double":
                return torch.rand(
                    *shape, requires_grad=True, device=torch.device(device)
                )
            elif attr["dtype"] == "int" or attr["dtype"] == "long":
                return torch.randint(
                    -10,
                    10,
                    tuple(shape),
                    requires_grad=True,
                    device=torch.device(device),
                )
        # Single value
        else:
            return torch.tensor(
                random.uniform(-10.0, 10.0),
                dtype=pytorch_dtype_map[attr["dtype"]],
                requires_grad=True,
                device=torch.device(device),
            )

    def create_float(attr: Dict[str, Any]):
        if "value" in attr:
            return attr["value"]
        return random.uniform(attr["value_range"][0], attr["value_range"][1])

    def create_int(attr: Dict[str, Any]):
        # check "value" key exists, attr["value"] = 0 could be eval to False
        if "value" in attr:
            return attr["value"]
        return random.randint(attr["value_range"][0], attr["value_range"][1])

    def create_str(attr: Dict[str, Any]):
        # check "value" key exists, attr["value"] = 0 could be eval to False
        if "value" in attr:
            return attr["value"]
        return ""

    def create_bool(attr: Dict[str, Any]):
        return attr["value"]

    def create_none(attr: Dict[str, Any]):
        return None

    def create_device(attr: Dict[str, Any]):
        return torch.device(attr["value"])

    def create_genericlist(attr: List[Any]):
        result = []
        for item in attr["value"]:
            result.append(arg_factory[item["type"]](item))
        return result

    def create_tuple(attr: List[Any]):
        result = create_genericlist(attr)
        return tuple(result)

    # Map of argument types to the create methods.
    arg_factory: Dict[str, Callable] = {
        "tensor": create_tensor,
        "float": create_float,
        "double": create_float,
        "int": create_int,
        "long": create_int,
        "none": create_none,
        "bool": create_bool,
        "device": create_device,
        "str": create_str,
        "genericlist": create_genericlist,
        "tuple": create_tuple,
    }
    return arg_factory[arg["type"]](arg)


# DefaultDataGenerator
class DefaultDataGenerator(DataGenerator):
    def __init__(self, cache: bool = False):
        super(DefaultDataGenerator, self).__init__()
        # keep track/cache last arg_config so we only generate data for
        # args that's different from previous iteration.
        self.cache = cache
        self.prev_config = None
        self.op_args = []
        self.op_kwargs = {}

    def _find_updates(self, config: Dict[str, Any]):
        if not self.prev_config:
            return (None, None)
        arg_updates = set()
        kwarg_updates = set()
        if "args" in config:
            for i, vals in enumerate(zip(self.prev_config["args"], config["args"])):
                if vals[0] != vals[1]:
                    arg_updates.add(i)
        if "kwargs" in config:
            for key in self.prev_config["kwargs"]:
                if self.prev_config["kwargs"][key] != config["kwargs"][key]:
                    kwarg_updates.add(key)

        logger.debug(f"  prev: {self.prev_config}")
        logger.debug(f"  curr: {config}")
        logger.debug(f"  updt: {arg_updates} {kwarg_updates}")
        return (arg_updates, kwarg_updates)

    def _generate_data(
        self,
        config: Dict[str, Any],
        device: str,
        arg_updates: Set[Any],
        kwarg_updates: Set[Any],
    ):
        if len(self.op_args) == 0:
            self.op_args = [None] * len(config["args"])
        if "args" in config:
            for i, arg in enumerate(config["args"]):
                if arg_updates:
                    if i in arg_updates:
                        self.op_args[i] = materialize_arg(arg, device)
                else:
                    self.op_args[i] = materialize_arg(arg, device)

        if "kwargs" in config:
            for key, arg in config["kwargs"].items():
                if kwarg_updates:
                    if key in kwarg_updates:
                        self.op_kwargs[key] = materialize_arg(arg, device)
                else:
                    self.op_kwargs[key] = materialize_arg(arg, device)

    def get_data(self, config: Dict[str, Any], device: str):
        if self.cache:
            # find the arg config that changed from previous iteration
            arg_updates, kwarg_updates = self._find_updates(config)
            # cache arg configs for next iteration to compare.
            self.prev_config = copy.deepcopy(config)
            self._generate_data(config, device, arg_updates, kwarg_updates)
        else:
            self._generate_data(config, device, None, None)

        return (self.op_args, self.op_kwargs)


register_data_generator("PyTorch::DefaultDataGenerator", DefaultDataGenerator)
