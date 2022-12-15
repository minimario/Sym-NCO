import torch.nn as nn
import torch.nn.intrinsic as nni

from typing import Union, Callable, Tuple, Dict, Optional, Type
from torch.ao.quantization.utils import Pattern

from torch.ao.quantization.utils import get_combined_dict


def fuse_conv_bn(is_qat, conv, bn):
    r"""Given the conv and bn modules, fuses them and returns the fused module

    Args:
        is_qat: a flag for whether we are using quantization aware training fusion
        or post training quantization fusion
        conv: Module instance of type conv2d/conv3d
        bn: Spatial BN instance that needs to be fused with the conv

    Examples::

        >>> m1 = nn.Conv2d(10, 20, 3)
        >>> b1 = nn.BatchNorm2d(20)
        >>> m2 = fuse_conv_bn(m1, b1)
    """
    assert(conv.training == bn.training),\
        "Conv and BN both must be in the same mode (train or eval)."

    fused_module_class_map = {
        nn.Conv1d: nni.ConvBn1d,
        nn.Conv2d: nni.ConvBn2d,
        nn.Conv3d: nni.ConvBn3d,
    }

    if is_qat:
        # TODO: remove the assert later
        assert conv.training, "qat is only supported when conv.training is True currently"
        assert bn.num_features == conv.out_channels, 'Output channel of Conv2d must match num_features of BatchNorm2d'
        assert bn.affine, 'Only support fusing BatchNorm2d with affine set to True'
        assert bn.track_running_stats, 'Only support fusing BatchNorm2d with tracking_running_stats set to True'
        fused_module_class = fused_module_class_map.get((type(conv)), None)
        if fused_module_class is not None:
            return fused_module_class(conv, bn)
        else:
            raise NotImplementedError("Cannot fuse train modules: {}".format((conv, bn)))
    else:
        return nn.utils.fuse_conv_bn_eval(conv, bn)

def fuse_conv_bn_relu(is_qat, conv, bn, relu):
    r"""Given the conv and bn modules, fuses them and returns the fused module

    Args:
        is_qat: a flag for whether we are using quantization aware training fusion
        or post training quantization fusion
        conv: Module instance of type conv2d/conv3d
        bn: Spatial BN instance that needs to be fused with the conv

    Examples::

        >>> m1 = nn.Conv2d(10, 20, 3)
        >>> b1 = nn.BatchNorm2d(20)
        >>> r1 = nn.ReLU(inplace=False)
        >>> m2 = fuse_conv_bn_relu(m1, b1, r1)
    """
    assert(conv.training == bn.training == relu.training),\
        "Conv and BN both must be in the same mode (train or eval)."
    fused_module : Optional[Type[nn.Sequential]] = None
    if is_qat:
        # TODO: remove the assert later
        assert conv.training, "qat is only supported when conv.training is True currently"
        map_to_fused_module_train = {
            nn.Conv1d: nni.ConvBnReLU1d,
            nn.Conv2d: nni.ConvBnReLU2d,
            nn.Conv3d: nni.ConvBnReLU3d,
        }
        assert bn.num_features == conv.out_channels, 'Output channel of Conv must match num_features of BatchNorm'
        assert bn.affine, 'Only support fusing BatchNorm with affine set to True'
        assert bn.track_running_stats, 'Only support fusing BatchNorm with tracking_running_stats set to True'
        fused_module = map_to_fused_module_train.get(type(conv), None)
        if fused_module is not None:
            return fused_module(conv, bn, relu)
        else:
            raise NotImplementedError("Cannot fuse train modules: {}".format((conv, bn, relu)))
    else:
        map_to_fused_module_eval = {
            nn.Conv1d: nni.ConvReLU1d,
            nn.Conv2d: nni.ConvReLU2d,
            nn.Conv3d: nni.ConvReLU3d,
        }
        fused_module = map_to_fused_module_eval.get(type(conv), None)
        if fused_module is not None:
            fused_conv = nn.utils.fusion.fuse_conv_bn_eval(conv, bn)
            return fused_module(fused_conv, relu)
        else:
            raise NotImplementedError("Cannot fuse eval modules: {}".format((conv, bn, relu)))

def fuse_linear_bn(is_qat, linear, bn):
    r"""Given the linear and bn modules, fuses them and returns the fused module

    Args:
        is_qat: a flag for whether we are using quantization aware training fusion
        or post training quantization fusion
        linear: Module instance of type Linear
        bn: BatchNorm1d instance that needs to be fused with the linear layer

    Examples::

        >>> m1 = nn.Linear(20, 10)
        >>> b1 = nn.BatchNorm1d(10)
        >>> m2 = fuse_linear_bn(m1, b1)
    """
    assert(linear.training == bn.training),\
        "Linear and BN both must be in the same mode (train or eval)."

    if is_qat:
        # TODO: remove the assert later
        assert linear.training, "qat is only supported when linear.training is True currently"
        raise Exception("Fusing Linear+BatchNorm not yet supported in training.")
    else:
        return nn.utils.fusion.fuse_linear_bn_eval(linear, bn)

def fuse_convtranspose_bn(is_qat, convt, bn):
    r"""Given ConvTranspose and bn modules, fuses them and returns the fused module

    Args:
        convt: Module instance of type ConvTransposeNd
        bn: BatchNormNd instance that needs to be fused with the linear layer.
            batch norm N should match the ConvTranspose N

    Examples::

        >>> m1 = nn.ConvTranspose2d(10, 20, 3)
        >>> b1 = nn.BatchNorm2d(20)
        >>> m2 = fuse_convtranspose_bn(m1, b1)
    """
    assert(convt.training == bn.training),\
        "ConvTranspose and BN both must be in the same mode (train or eval)."

    if is_qat:
        assert convt.training, "qat is only supported when convt.training is True currently"
        raise Exception("Fusing ConvTranspose+BatchNorm not yet supported in training.")
    else:
        return nn.utils.fusion.fuse_conv_bn_eval(convt, bn, transpose=True)

def sequential_wrapper2(sequential):
    """ Given a sequential class for two modules, return a function that takes
    is_qat, and then two modules as argument, that ignores the is_qat flag
    and always returns the sequential that combines the two input modules
    """
    def fuser_method(is_qat, m1, m2):
        return sequential(m1, m2)
    return fuser_method

DEFAULT_OP_LIST_TO_FUSER_METHOD: Dict[Tuple, Union[nn.Sequential, Callable]] = {
    (nn.Conv1d, nn.BatchNorm1d): fuse_conv_bn,
    (nn.Conv1d, nn.BatchNorm1d, nn.ReLU): fuse_conv_bn_relu,
    (nn.Conv2d, nn.BatchNorm2d): fuse_conv_bn,
    (nn.Conv2d, nn.BatchNorm2d, nn.ReLU): fuse_conv_bn_relu,
    (nn.Conv3d, nn.BatchNorm3d): fuse_conv_bn,
    (nn.Conv3d, nn.BatchNorm3d, nn.ReLU): fuse_conv_bn_relu,
    (nn.Conv1d, nn.ReLU): sequential_wrapper2(nni.ConvReLU1d),
    (nn.Conv2d, nn.ReLU): sequential_wrapper2(nni.ConvReLU2d),
    (nn.Conv3d, nn.ReLU): sequential_wrapper2(nni.ConvReLU3d),
    (nn.Linear, nn.BatchNorm1d): fuse_linear_bn,
    (nn.Linear, nn.ReLU): sequential_wrapper2(nni.LinearReLU),
    (nn.BatchNorm2d, nn.ReLU): sequential_wrapper2(nni.BNReLU2d),
    (nn.BatchNorm3d, nn.ReLU): sequential_wrapper2(nni.BNReLU3d),
    (nn.ConvTranspose1d, nn.BatchNorm1d): fuse_convtranspose_bn,
    (nn.ConvTranspose2d, nn.BatchNorm2d): fuse_convtranspose_bn,
    (nn.ConvTranspose3d, nn.BatchNorm3d): fuse_convtranspose_bn,
}

def get_fuser_method(op_list, additional_fuser_method_mapping=None):
    ''' Get fuser method for the given list of module types,
    return None if fuser method does not exist
    '''
    if additional_fuser_method_mapping is None:
        additional_fuser_method_mapping = dict()
    all_mappings = get_combined_dict(DEFAULT_OP_LIST_TO_FUSER_METHOD,
                                     additional_fuser_method_mapping)
    fuser_method = all_mappings.get(op_list, None)
    assert fuser_method is not None, "did not find fuser method for: {} ".format(op_list)
    return fuser_method

def reverse_sequential_wrapper2(sequential):
    """ Given a sequential class for two modules, return a function that takes
    is_qat, and then two modules as argument, that ignores the is_qat flag
    and always returns the sequential that combines the two input modules, with
    the order of two inputs reversed
    """
    def fuser_method(is_qat, m1, m2):
        return sequential(m2, m1)
    return fuser_method

def reverse2(f):
    def reversed(is_qat, x, y):
        return f(is_qat, y, x)
    return reversed

def reverse3(f):
    def reversed(is_qat, x, w):
        y, z = w
        return f(is_qat, z, y, x)
    return reversed

DEFAULT_PATTERN_TO_FUSER_METHOD: Dict[Pattern, Union[nn.Sequential, Callable]] = {
    (nn.BatchNorm1d, nn.Conv1d): reverse2(fuse_conv_bn),
    (nn.ReLU, (nn.BatchNorm1d, nn.Conv1d)): reverse3(fuse_conv_bn_relu),
    (nn.BatchNorm2d, nn.Conv2d): reverse2(fuse_conv_bn),
    (nn.ReLU, (nn.BatchNorm2d, nn.Conv2d)): reverse3(fuse_conv_bn_relu),
    (nn.BatchNorm3d, nn.Conv3d): reverse2(fuse_conv_bn),
    (nn.ReLU, (nn.BatchNorm3d, nn.Conv3d)): reverse3(fuse_conv_bn_relu),
    (nn.ReLU, nn.Conv1d): reverse_sequential_wrapper2(nni.ConvReLU1d),
    (nn.ReLU, nn.Conv2d): reverse_sequential_wrapper2(nni.ConvReLU2d),
    (nn.ReLU, nn.Conv3d): reverse_sequential_wrapper2(nni.ConvReLU3d),
    (nn.BatchNorm1d, nn.Linear): reverse2(fuse_linear_bn),
    (nn.ReLU, nn.Linear): reverse_sequential_wrapper2(nni.LinearReLU),
    (nn.ReLU, nn.BatchNorm2d): reverse_sequential_wrapper2(nni.BNReLU2d),
    (nn.ReLU, nn.BatchNorm3d): reverse_sequential_wrapper2(nni.BNReLU3d),
    (nn.BatchNorm1d, nn.ConvTranspose1d): reverse2(fuse_convtranspose_bn),
    (nn.BatchNorm2d, nn.ConvTranspose2d): reverse2(fuse_convtranspose_bn),
    (nn.BatchNorm3d, nn.ConvTranspose3d): reverse2(fuse_convtranspose_bn),
}

def get_fuser_method_new(
        op_pattern: Pattern,
        fuser_method_mapping: Optional[Dict[Pattern, Union[nn.Sequential, Callable]]] = None):
    """ This will be made defult after we deparate the get_fuser_method
    Would like to implement this first and have a separate PR for deprecation
    """
    if fuser_method_mapping is None:
        fuser_method_mapping = DEFAULT_PATTERN_TO_FUSER_METHOD

    fuser_method = fuser_method_mapping.get(op_pattern, None)
    assert fuser_method is not None, "did not find fuser method for: {} ".format(op_pattern)
    return fuser_method