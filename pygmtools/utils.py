import functools
import importlib
import copy

import pygmtools

NOT_IMPLEMENTED_MSG = \
    'The backend function for {} is not implemented. ' \
    'If you are a user, please use other backends as workarounds.' \
    'If you are a developer, it will be truly appreciated if you could develop and share your' \
    ' implementation with the community! See our Github: https://github.com/Thinklab-SJTU/pygmtools'


def build_aff_mat(node_feat1, edge_feat1, connectivity1, node_feat2, edge_feat2, connectivity2,
                  n1=None, ne1=None, n2=None, ne2=None,
                  node_aff_fn=None, edge_aff_fn=None,
                  backend=None):
    r"""
    Build affinity matrix for graph matching from input node/edge features. The affinity matrix encodes both node-wise
    and edge-wise affinities and formulates the Quadratic Assignment Problem (QAP), which is the mathematical form of
    graph matching.

    :param node_feat1: :math:`(b\times n_1 \times f_{node})` the node feature of graph1
    :param edge_feat1: :math:`(b\times ne_1 \times f_{edge})` the edge feature of graph1
    :param connectivity1: :math:`(b\times ne_1 \times 2)` sparse connectivity information of graph 1.
                          ``connectivity1[i, j, 0]`` is the starting node index of edge ``j`` at batch ``i``, and
                          ``connectivity1[i, j, 1]`` is the ending node index of edge ``j`` at batch ``i``
    :param node_feat2: :math:`(b\times n_2 \times f_{node})` the node feature of graph2
    :param edge_feat2: :math:`(b\times ne_2 \times f_{edge})` the edge feature of graph2
    :param connectivity2: :math:`(b\times ne_2 \times 2)` sparse connectivity information of graph 2.
                          ``connectivity2[i, j, 0]`` is the starting node index of edge ``j`` at batch ``i``, and
                          ``connectivity2[i, j, 1]`` is the ending node index of edge ``j`` at batch ``i``
    :param n1: :math:`(b)` number of nodes in graph1. If not given, it will be inferred based on the shape of
               ``node_feat1`` or the values in ``connectivity1``
    :param ne1: :math:`(b)` number of edges in graph1. If not given, it will be inferred based on the shape of
               ``edge_feat1``
    :param n2: :math:`(b)` number of nodes in graph2. If not given, it will be inferred based on the shape of
               ``node_feat2`` or the values in ``connectivity2``
    :param ne2: :math:`(b)` number of edges in graph2. If not given, it will be inferred based on the shape of
               ``edge_feat2``
    :param node_aff_fn: (default: inner_prod_aff_fn) the node affinity function with the characteristic
                        ``node_aff_fn(2D Tensor, 2D Tensor) -> 2D Tensor``, which accepts two node feature tensors and
                        outputs the node-wise affinity tensor. See :func:`~pygmtools.utils.inner_prod_aff_fn` as an
                        example.
    :param edge_aff_fn: (default: inner_prod_aff_fn) the edge affinity function with the characteristic
                        ``edge_aff_fn(2D Tensor, 2D Tensor) -> 2D Tensor``, which accepts two edge feature tensors and
                        outputs the edge-wise affinity tensor. See :func:`~pygmtools.utils.inner_prod_aff_fn` as an
                        example.
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: :math:`(b\times n_1n_2 \times n_1n_2)` the affinity matrix

    Example for numpy backend::

        >>> import numpy as np
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'numpy'

        # Generate a batch of graphs
        >>> batch_size = 10
        >>> A1 = np.random.rand(batch_size, 4, 4)
        >>> A2 = np.random.rand(batch_size, 4, 4)
        >>> n1 = n2 = np.repeat([4], batch_size)

        # Build affinity matrix by the default inner-product function
        >>> conn1, edge1, ne1 = pygm.utils.dense_to_sparse(A1)
        >>> conn2, edge2, ne2 = pygm.utils.dense_to_sparse(A2)
        >>> K = pygm.utils.build_aff_mat(None, edge1, conn1, None, edge2, conn2, n1, ne1, n2, ne2)

        # Build affinity matrix by gaussian kernel
        >>> import functools
        >>> gaussian_aff = functools.partial(pygm.utils.gaussian_aff_fn, sigma=1.)
        >>> K2 = pygm.utils.build_aff_mat(None, edge1, conn1, None, edge2, conn2, n1, ne1, n2, ne2, edge_aff_fn=gaussian_aff)

        # Build affinity matrix based on node features
        >>> F1 = np.random.rand(batch_size, 4, 10)
        >>> F2 = np.random.rand(batch_size, 4, 10)
        >>> K3 = pygm.utils.build_aff_mat(F1, edge1, conn1, F2, edge2, conn2, n1, ne1, n2, ne2, edge_aff_fn=gaussian_aff)

        # The affinity matrices K, K2, K3 can be further processed by GM solvers

    Example for Pytorch backend::

        >>> import torch
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'pytorch'

        # Generate a batch of graphs
        >>> batch_size = 10
        >>> A1 = torch.rand(batch_size, 4, 4)
        >>> A2 = torch.rand(batch_size, 4, 4)
        >>> n1 = n2 = torch.tensor([4] * batch_size)

        # Build affinity matrix by the default inner-product function
        >>> conn1, edge1, ne1 = pygm.utils.dense_to_sparse(A1)
        >>> conn2, edge2, ne2 = pygm.utils.dense_to_sparse(A2)
        >>> K = pygm.utils.build_aff_mat(None, edge1, conn1, None, edge2, conn2, n1, ne1, n2, ne2)

        # Build affinity matrix by gaussian kernel
        >>> import functools
        >>> gaussian_aff = functools.partial(pygm.utils.gaussian_aff_fn, sigma=1.)
        >>> K2 = pygm.utils.build_aff_mat(None, edge1, conn1, None, edge2, conn2, n1, ne1, n2, ne2, edge_aff_fn=gaussian_aff)

        # Build affinity matrix based on node features
        >>> F1 = torch.rand(batch_size, 4, 10)
        >>> F2 = torch.rand(batch_size, 4, 10)
        >>> K3 = pygm.utils.build_aff_mat(F1, edge1, conn1, F2, edge2, conn2, n1, ne1, n2, ne2, edge_aff_fn=gaussian_aff)

        # The affinity matrices K, K2, K3 can be further processed by GM solvers
    """
    if backend is None:
        backend = pygmtools.BACKEND

    # check the correctness of input
    batch_size = None
    if node_feat1 is not None or node_feat2 is not None:
        assert all([_ is not None for _ in (node_feat1, node_feat2)]), \
            'The following arguments must all be given if you want to compute node-wise affinity: ' \
            'node_feat1, node_feat2'
        _check_data_type(node_feat1, backend)
        _check_data_type(node_feat2, backend)
        assert all([_check_shape(_, 3, backend) for _ in (node_feat1, node_feat2)]), \
            f'The shape of the following tensors are illegal, expected 3-dimensional, ' \
            f'got node_feat1={len(_get_shape(node_feat1))}d; node_feat2={len(_get_shape(node_feat2))}d!'
        if batch_size is None:
            batch_size = _get_shape(node_feat1)[0]
        assert _get_shape(node_feat1)[0] == _get_shape(node_feat2)[0] == batch_size, 'batch size mismatch'
    if edge_feat1 is not None or edge_feat2 is not None:
        assert all([_ is not None for _ in (edge_feat1, edge_feat2, connectivity1, connectivity2)]), \
            'The following arguments must all be given if you want to compute edge-wise affinity: ' \
            'edge_feat1, edge_feat2, connectivity1, connectivity2'
        assert all([_check_shape(_, 3, backend) for _ in (edge_feat1, edge_feat2, connectivity1, connectivity2)]), \
            f'The shape of the following tensors are illegal, expected 3-dimensional, ' \
            f'got edge_feat1:{len(_get_shape(edge_feat1))}d; edge_feat2:{len(_get_shape(edge_feat2))}d; ' \
            f'connectivity1:{len(_get_shape(connectivity1))}d; connectivity2:{len(_get_shape(connectivity2))}d!'
        assert _get_shape(connectivity1)[2] == _get_shape(connectivity1)[2] == 2, \
            'the 3rd dimension of connectivity1, connectivity2 must be 2-dimensional'
        if batch_size is None:
            batch_size = _get_shape(edge_feat1)[0]
        assert _get_shape(edge_feat1)[0] == _get_shape(edge_feat2)[0] == _get_shape(connectivity1)[0] == \
               _get_shape(connectivity2)[0] == batch_size, 'batch size mismatch'

    # assign the default affinity functions if not given
    if node_aff_fn is None:
        node_aff_fn = functools.partial(inner_prod_aff_fn, backend=backend)
    if edge_aff_fn is None:
        edge_aff_fn = functools.partial(inner_prod_aff_fn, backend=backend)

    node_aff = node_aff_fn(node_feat1, node_feat2) if node_feat1 is not None else None
    edge_aff = edge_aff_fn(edge_feat1, edge_feat2) if edge_feat1 is not None else None

    return _aff_mat_from_node_edge_aff(node_aff, edge_aff, connectivity1, connectivity2, n1, n2, ne1, ne2, backend=backend)


def inner_prod_aff_fn(feat1, feat2, backend=None):
    r"""
    Inner product affinity function. The affinity is defined as

    .. math::
        \mathbf{f}_1^\top \cdot \mathbf{f}_2

    :param feat1: :math:`(b\times n_1 \times f)` the feature vectors :math:`\mathbf{f}_1`
    :param feat2: :math:`(b\times n_2 \times f)` the feature vectors :math:`\mathbf{f}_2`
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: :math:`(b\times n_1\times n_2)` element-wise inner product affinity matrix
    """
    if backend is None:
        backend = pygmtools.BACKEND

    _check_data_type(feat1, backend)
    _check_data_type(feat2, backend)
    args = (feat1, feat2)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.inner_prod_aff_fn
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def gaussian_aff_fn(feat1, feat2, sigma=1., backend=None):
    r"""
    Gaussian kernel affinity function. The affinity is defined as

    .. math::
        \exp(-\frac{(\mathbf{f}_1 - \mathbf{f}_2)^2}{\sigma})

    :param feat1: :math:`(b\times n_1 \times f)` the feature vectors :math:`\mathbf{f}_1`
    :param feat2: :math:`(b\times n_2 \times f)` the feature vectors :math:`\mathbf{f}_2`
    :param sigma: (default: 1) the parameter :math:`\sigma` in Gaussian kernel
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return:  :math:`(b\times n_1\times n_2)` element-wise Gaussian affinity matrix
    """
    if backend is None:
        backend = pygmtools.BACKEND

    _check_data_type(feat1, backend)
    _check_data_type(feat2, backend)
    args = (feat1, feat2, sigma)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.gaussian_aff_fn
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def build_batch(input, return_ori_dim=False, backend=None):
    r"""
    Build a batched tensor from a list of tensors. If the list of tensors are with different sizes of dimensions, it
    will be padded to the largest dimension.

    The batched tensor and the number of original dimensions will be returned.

    :param input: list of input tensors
    :param return_ori_dim: (default: False) return the original dimension
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: batched tensor, (if ``return_ori_dim=True``) a list of the original dimensions

    Example for numpy backend::

        >>> import numpy as np
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'numpy'

        # batched adjacency matrices
        >>> A1 = np.random.rand(4, 4)
        >>> A2 = np.random.rand(5, 5)
        >>> A3 = np.random.rand(3, 3)
        >>> batched_A, ori_shape = pygm.utils.build_batch([A1, A2, A3], return_ori_dim=True)
        >>> batched_A.shape
        (3, 5, 5)
        >>> ori_shape
        ([4, 5, 3], [4, 5, 3])

        # batched node features (feature dimension=10)
        >>> F1 = np.random.rand(4, 10)
        >>> F2 = np.random.rand(5, 10)
        >>> F3 = np.random.rand(3, 10)
        >>> batched_F = pygm.utils.build_batch([F1, F2, F3])
        >>> batched_F.shape
        (3, 5, 10)

    Example for Pytorch backend::

        >>> import torch
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'pytorch'

        # batched adjacency matrices
        >>> A1 = torch.rand(4, 4)
        >>> A2 = torch.rand(5, 5)
        >>> A3 = torch.rand(3, 3)
        >>> batched_A, ori_shape = pygm.utils.build_batch([A1, A2, A3], return_ori_dim=True)
        >>> batched_A.shape
        torch.Size([3, 5, 5])
        >>> ori_shape
        (tensor([4, 5, 3]), tensor([4, 5, 3]))

        # batched node features (feature dimension=10)
        >>> F1 = torch.rand(4, 10)
        >>> F2 = torch.rand(5, 10)
        >>> F3 = torch.rand(3, 10)
        >>> batched_F = pygm.utils.build_batch([F1, F2, F3])
        >>> batched_F.shape
        torch.Size([3, 5, 10])

    """
    if backend is None:
        backend = pygmtools.BACKEND
    for item in input:
        _check_data_type(item, backend)
    args = (input, return_ori_dim)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.build_batch
    except ImportError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def dense_to_sparse(dense_adj, backend=None):
    r"""
    Convert a dense connectivity/adjacency matrix to a sparse connectivity/adjacency matrix and an edge weight tensor.

    :param dense_adj: :math:`(b\times n\times n)` the dense adjacency matrix. This function also supports non-batched
                      input where the batch dimension ``b`` is ignored
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: :math:`(b\times ne\times 2)` sparse connectivity matrix, :math:`(b\times ne\times 1)` edge weight tensor,
             :math:`(b)` number of edges

    Example for numpy backend::

        >>> import numpy as np
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'numpy'
        >>> np.random.seed(0)

        >>> batch_size = 10
        >>> A = np.random.rand(batch_size, 4, 4)
        >>> A[:, np.arange(4), np.arange(4)] = 0 # remove the diagonal elements
        >>> A.shape
        (10, 4, 4)

        >>> conn, edge, ne = pygm.utils.dense_to_sparse(A)
        >>> conn.shape # connectivity: (batch x num_edge x 2)
        (10, 12, 2)

        >>> edge.shape # edge feature (batch x num_edge x feature_dim)
        (10, 12, 1)

        >>> ne
        [12, 12, 12, 12, 12, 12, 12, 12, 12, 12]

    Example for Pytorch backend::

        >>> import torch
        >>> import pygmtools as pygm
        >>> pygm.BACKEND = 'pytorch'
        >>> _ = torch.manual_seed(0)

        >>> batch_size = 10
        >>> A = torch.rand(batch_size, 4, 4)
        >>> torch.diagonal(A, dim1=1, dim2=2)[:] = 0 # remove the diagonal elements
        >>> A.shape
        torch.Size([10, 4, 4])

        >>> conn, edge, ne = pygm.utils.dense_to_sparse(A)
        >>> conn.shape # connectivity: (batch x num_edge x 2)
        torch.Size([10, 12, 2])

        >>> edge.shape # edge feature (batch x num_edge x feature_dim)
        torch.Size([10, 12, 1])

        >>> ne
        tensor([12, 12, 12, 12, 12, 12, 12, 12, 12, 12])

    """
    if backend is None:
        backend = pygmtools.BACKEND
    _check_data_type(dense_adj, backend)
    if _check_shape(dense_adj, 2, backend):
        dense_adj = _unsqueeze(dense_adj, 0, backend)
        non_batched_input = True
    elif _check_shape(dense_adj, 3, backend):
        non_batched_input = False
    else:
        raise ValueError(f'the input argument dense_adj is expected to be 2-dimensional or 3-dimensional, got '
                         f'dense_adj:{len(_get_shape(dense_adj))}!')

    args = (dense_adj,)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.dense_to_sparse
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )

    result = fn(*args)
    if non_batched_input:
        return _squeeze(result[0], 0, backend), _squeeze(result[1], 0, backend)
    else:
        return result


def compute_affinity_score(X, K, backend=None):
    r"""
    Compute the affinity score of graph matching. It is the objective score of the corresponding Quadratic Assignment
    Problem.

    .. math::

        \texttt{vec}(\mathbf{X})^\top \mathbf{K} \texttt{vec}(\mathbf{X})

    here :math:`\texttt{vec}` means column-wise vectorization.

    :param X: :math:`(b\times n_1 \times n_2)` the permutation matrix that represents the matching result
    :param K: :math:`(b\times n_1n_2 \times n_1n_2)` the affinity matrix
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: :math:`(b)` the objective score

    .. note::

       This function also supports non-batched input if the first dimension of ``X, K`` is removed.

    """
    if backend is None:
        backend = pygmtools.BACKEND
    _check_data_type(X, backend)
    _check_data_type(K, backend)
    if _check_shape(X, 2, backend) and _check_shape(K, 2, backend):
        X = _unsqueeze(X, 0, backend)
        K = _unsqueeze(K, 0, backend)
        non_batched_input = True
    elif _check_shape(X, 3, backend) and _check_shape(X, 3, backend):
        non_batched_input = False
    else:
        raise ValueError(f'the input argument K, X are expected to have the same number of dimensions (=2 or 3), got'
                         f'X:{len(_get_shape(X))} and K:{len(_get_shape(K))}!')
    args = (X, K)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.compute_affinity_score
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )

    result = fn(*args)
    if non_batched_input:
        return _squeeze(result, 0, backend)
    else:
        return result


def to_numpy(input, backend=None):
    r"""
    Convert a tensor to a numpy ndarray.
    This is the helper function to convert tensors across different backends via numpy.

    :param input: input tensor/:mod:`~pygmtools.utils.MultiMatchingResult`
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: numpy ndarray
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input,)
    # pygmtools built-in types
    if type(input) is MultiMatchingResult:
        fn = MultiMatchingResult.to_numpy
    # tf/torch/.. tensor types
    else:
        try:
            mod = importlib.import_module(f'pygmtools.{backend}_backend')
            fn = mod.to_numpy
        except ModuleNotFoundError and AttributeError:
            raise NotImplementedError(
                NOT_IMPLEMENTED_MSG.format(backend)
            )
    return fn(*args)


def from_numpy(input, device=None, backend=None):
    r"""
    Convert a numpy ndarray to a tensor.
    This is the helper function to convert tensors across different backends via numpy.

    :param input: input ndarray/:mod:`~pygmtools.utils.MultiMatchingResult`
    :param device: (default: None) the target device
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: tensor for the backend
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, device)
    # pygmtools built-in types
    if type(input) is MultiMatchingResult:
        fn = functools.partial(MultiMatchingResult.from_numpy, new_backend=backend)
    # tf/torch/.. tensor types
    else:
        try:
            mod = importlib.import_module(f'pygmtools.{backend}_backend')
            fn = mod.from_numpy
        except ModuleNotFoundError and AttributeError:
            raise NotImplementedError(
                NOT_IMPLEMENTED_MSG.format(backend)
            )
    return fn(*args)


def generate_isomorphic_graphs(node_num, graph_num=2, node_feat_dim=0, backend=None):
    r"""
    Generate a set of isomorphic graphs, for testing purposes and examples.

    :param node_num: number of nodes in each graph
    :param graph_num: (default: 2) number of graphs
    :param node_feat_dim: (default: 0) number of node feature dimensions
    :param backend: (default: ``pygmtools.BACKEND`` variable) the backend for computation.
    :return: if ``graph_num==2``, this function returns :math:`(m\times n \times n)` the adjacency matrix, and
             :math:`(n \times n)` the permutation matrix;

             else, this function returns :math:`(m\times n \times n)` the adjacency matrix, and
             :math:`(m\times m\times n \times n)` the multi-matching permutation matrix
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (node_num, graph_num, node_feat_dim)
    assert node_num > 0 and graph_num >= 2, "input data not understood."
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod.generate_isomorphic_graphs
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    if node_feat_dim > 0:
        As, X_gt, Fs = fn(*args)
        if graph_num == 2:
            return As, X_gt[0, 1], Fs
        else:
            return As, X_gt, Fs
    else:
        As, X_gt = fn(*args)
        if graph_num == 2:
            return As, X_gt[0, 1]
        else:
            return As, X_gt


class MultiMatchingResult:
    r"""
    A memory-efficient class for multi-graph matching results. For non-cycle consistent results, the dense storage
    for :math:`m` graphs with :math:`n` nodes requires a size of :math:`(m\times m \times n \times n)`, and this
    implementation requires :math:`((m-1)\times m \times n \times n / 2)`. For cycle consistent result, this
    implementation requires only :math:`(m\times n\times n)`.

    Numpy Example:

        >>> import numpy as np
        >>> import pygmtools as pygm
        >>> np.random.seed(0)

        >>> X = pygm.utils.MultiMatchingResult(backend='numpy')
        >>> X[0, 1] = np.zeros((4, 4))
        >>> X[0, 1][np.arange(0, 4, dtype=np.int64), np.random.permutation(4)] = 1
        >>> X
        MultiMatchingResult:
        {'0,1': array([[0., 0., 1., 0.],
               [0., 0., 0., 1.],
               [0., 1., 0., 0.],
               [1., 0., 0., 0.]])}
        >>> X[1, 0]
        array([[0., 0., 0., 1.],
               [0., 0., 1., 0.],
               [1., 0., 0., 0.],
               [0., 1., 0., 0.]])
    """
    def __init__(self, cycle_consistent=False, backend=None):
        self.match_dict = {}
        self._cycle_consistent = cycle_consistent
        if backend is None:
            self.backend = pygmtools.BACKEND
        else:
            self.backend = backend

    def __getitem__(self, item):
        assert len(item) == 2, "key should be the indices of two graphs, e.g. (0, 1)"
        idx1, idx2 = item
        if self._cycle_consistent:
            return _mm(self.match_dict[idx1], _transpose(self.match_dict[idx2], 0, 1, self.backend), self.backend)
        else:
            if idx1 < idx2:
                return self.match_dict[f'{idx1},{idx2}']
            else:
                return _transpose(self.match_dict[f'{idx2},{idx1}'], 0, 1, self.backend)

    def __setitem__(self, key, value):
        if self._cycle_consistent:
            assert type(key) is int, "key should be the index of one graph, and value should be the matching to universe"
            self.match_dict[key] = value
        else:
            assert len(key) == 2, "key should be the indices of two graphs, e.g. (0, 1)"
            idx1, idx2 = key
            if idx1 < idx2:
                self.match_dict[f'{idx1},{idx2}'] = value
            else:
                self.match_dict[f'{idx2},{idx1}'] = _transpose(value, 0, 1, self.backend)

    def __str__(self):
        return 'MultiMatchingResult:\n' + self.match_dict.__str__()

    def __repr__(self):
        return 'MultiMatchingResult:\n' + self.match_dict.__repr__()

    @staticmethod
    def from_numpy(data, new_backend):
        r"""
        Convert a numpy-backend MultiMatchingResult data to another backend.

        :param data: the numpy-backend data
        :param new_backend: the target backend
        :return: a new MultiMatchingResult instance for ``new_backend``
        """
        new_data = copy.deepcopy(data)
        new_data.from_numpy_(new_backend)
        return new_data

    @staticmethod
    def to_numpy(data):
        r"""
        Convert an any-type MultiMatchingResult to numpy backend.

        :param data: the any-type data
        :return: a new MultiMatchingResult instance for numpy
        """
        new_data = copy.deepcopy(data)
        new_data.to_numpy_()
        return new_data

    def from_numpy_(self, new_backend):
        """
        In-place operation for :func:`~pygmtools.utils.MultiMatchingResult.from_numpy`.
        """
        if self.backend != 'numpy':
            raise ValueError('Attempting to convert from non-numpy data.')
        self.backend = new_backend
        for k, v in self.match_dict.items():
            self.match_dict[k] = from_numpy(v, self.backend)
    
    def to_numpy_(self):
        """
        In-place operation for :func:`~pygmtools.utils.MultiMatchingResult.to_numpy`.
        """
        self.backend = 'numpy'
        for k, v in self.match_dict.items():
            self.match_dict[k] = to_numpy(v, self.backend)


###################################################
#   Private Functions that Unseeable from Users   #
###################################################


def _aff_mat_from_node_edge_aff(node_aff, edge_aff, connectivity1, connectivity2,
                                n1, n2, ne1, ne2,
                                backend=None):
    r"""
    Build affinity matrix K from node and edge affinity matrices.

    :param node_aff: :math:`(b\times n_1 \times n_2)` the node affinity matrix
    :param edge_aff: :math:`(b\times ne_1 \times ne_2)` the edge affinity matrix
    :param connectivity1: :math:`(b\times ne_1 \times 2)` sparse connectivity information of graph 1
    :param connectivity2: :math:`(b\times ne_2 \times 2)` sparse connectivity information of graph 2
    :param n1: :math:`(b)` number of nodes in graph1. If not given, it will be inferred based on the shape of
               ``node_feat1`` or the values in ``connectivity1``
    :param ne1: :math:`(b)` number of edges in graph1. If not given, it will be inferred based on the shape of
               ``edge_feat1``
    :param n2: :math:`(b)` number of nodes in graph2. If not given, it will be inferred based on the shape of
               ``node_feat2`` or the values in ``connectivity2``
    :param ne2: :math:`(b)` number of edges in graph2. If not given, it will be inferred based on the shape of
               ``edge_feat2``
    :return: :math:`(b\times n_1n_2 \times n_1n_2)` the affinity matrix
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (node_aff, edge_aff, connectivity1, connectivity2, n1, n2, ne1, ne2)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._aff_mat_from_node_edge_aff
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _check_data_type(input, backend=None):
    r"""
    Check whether the input data meets the backend. If not met, it will raise an ValueError

    :param input: input data (must be Tensor/ndarray)
    :return: None
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, )
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._check_data_type
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _check_shape(input, num_dim, backend=None):
    r"""
    Check the shape of the input tensor

    :param input: the input tensor
    :param num_dim: number of dimensions
    :return: True or False
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, num_dim)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._check_shape
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _get_shape(input, backend=None):
    r"""
    Get the shape of the input tensor

    :param input: the input tensor
    :return: a list of ints indicating the shape
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input,)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._get_shape
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _squeeze(input, dim, backend=None):
    r"""
    Squeeze the input tensor at the given dimension. This function is expected to behave the same as torch.squeeze

    :param input: input tensor
    :param dim: squeezed dimension
    :return: squeezed tensor
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, dim)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._squeeze
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _unsqueeze(input, dim, backend=None):
    r"""
    Unsqueeze the input tensor at the given dimension. This function is expected to behave the same as torch.unsqueeze

    :param input: input tensor
    :param dim: unsqueezed dimension
    :return: unsqueezed tensor
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, dim)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._unsqueeze
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)


def _transpose(input, dim1, dim2, backend=None):
    r"""
    Swap the dim1 and dim2 dimensions of the input tensor.

    :param input: input tensor
    :param dim1: swapped dimension 1
    :param dim2: swapped dimension 2
    :return: transposed tensor
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input, dim1, dim2)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._transpose
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)

def _mm(input1, input2, backend=None):
    r"""
    Matrix multiplication.

    :param input1: input tensor 1
    :param input2: input tensor 2
    :return: multiplication result
    """
    if backend is None:
        backend = pygmtools.BACKEND
    args = (input1, input2)
    try:
        mod = importlib.import_module(f'pygmtools.{backend}_backend')
        fn = mod._mm
    except ModuleNotFoundError and AttributeError:
        raise NotImplementedError(
            NOT_IMPLEMENTED_MSG.format(backend)
        )
    return fn(*args)