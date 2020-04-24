"""Statistical Manifold of beta distributions with the Fisher metric."""

from scipy.integrate import odeint
from scipy.integrate import solve_bvp
from scipy.stats import beta

import geomstats.backend as gs
import geomstats.error
from geomstats.geometry.embedded_manifold import EmbeddedManifold
from geomstats.geometry.euclidean import Euclidean
from geomstats.geometry.riemannian_metric import RiemannianMetric
from geomstats.geometry.symmetric_matrices import SymmetricMatrices

N_STEPS = 100
EPSILON = 1e-6


class BetaDistributions(EmbeddedManifold):
    r"""Class for the manifold of beta distributions.

    This is :math: Beta = `R_+^* \times R_+^*`.
    """

    def __init__(self):
        super(BetaDistributions, self).__init__(
            dim=2, embedding_manifold=Euclidean(dim=2))
        self.metric = BetaMetric()

    def belongs(self, point):
        """Evaluate if a point belongs to the manifold of beta distributions.

        The statistical manifold of beta distributions is the upper right
        quadrant of the euclidean 2-plane.

        Parameters
        ----------
        point : array-like, shape=[n_samples, 2]
            the point of which to check whether it belongs to Beta

        Returns
        -------
        belongs : array-like, shape=[n_samples, 1]
            array of booleans indicating whether point belongs the Beta
        """
        point_dim = point.shape[-1]
        belongs = point_dim == self.dim
        belongs = gs.logical_and(
            belongs, gs.all(gs.greater(point, 0.), axis=-1))
        return belongs

    @staticmethod
    def random_uniform(n_samples=1, bound=5.):
        """Sample parameters of beta distributions.

        The uniform distribution on [0, bound]^2 is used.

        Parameters
        ----------
        n_samples : int, optional
        bound : float, optional
            scalar to scale samples

        Returns
        -------
        samples : array-like, shape=[n_samples, 2]
        """
        if n_samples == 1:
            return bound * gs.random.rand(2)
        return bound * gs.random.rand(n_samples, 2)

    def sample(self, point, n_samples=1):
        """Sample from the beta distribution.

        Sample from the beta distribution with parameters provided by point.

        Parameters
        ----------
        point : array-like, shape [n_points, 2]
        n_samples : int
            the number of points to sample with each pair of parameter in
            point

        Returns
        -------
        samples : array-like, shape=[n_points, n_samples]
        """
        point = gs.to_ndarray(point, to_ndim=2)
        geomstats.error.check_belongs(
            point, self, 'beta_distributions')
        samples = []
        for param_a, param_b in point:
            samples.append(gs.array(
                beta.rvs(param_a, param_b, size=n_samples)))
        return samples[0] if len(point) == 1 else gs.stack(samples)

    @staticmethod
    def maximum_likelihood_fit(data, loc=0, scale=1):
        """Estimate parameters from samples.

        This a wrapper around scipy's maximum likelihood estimator to
        estimate the parameters of a beta distribution from samples.

        Parameters
        ----------
        data : array-like, shape=[n_distributions, n_samples]
            the data to estimate parameters from. Arrays of
            different length may be passed.
        loc : float, optional
            the location parameter of the distribution to estimate parameters
            from. It is kept fixed during optimization
            default: 0
        scale : float, optional
            the scale parameter of the distribution to estimate parameters
            from. It is kept fixed during optimization
            default: 1
        Returns
        -------
        parameter : array-like, shape=[n_samples, 2]
        """
        data = gs.cast(data, gs.float32)
        data = gs.to_ndarray(
            gs.where(data == 1., gs.array(1. - EPSILON), data), to_ndim=2)
        parameters = []
        for sample in data:
            param_a, param_b, _, _ = beta.fit(sample, floc=loc, fscale=scale)
            parameters.append(gs.array([param_a, param_b]))
        return parameters[0] if len(data) == 1 else gs.stack(parameters)


class BetaMetric(RiemannianMetric):
    """Class for the Fisher information metric on beta distributions."""

    def __init__(self):
        super(BetaMetric, self).__init__(dim=2)

    @staticmethod
    def metric_det(param_a, param_b):
        """Compute the determinant of the metric.

        Parameters
        ----------
        param_a : array-like, shape=[n_samples,]
        param_b : array-like, shape=[n_samples,]

        Returns
        -------
        metric_det : array-like, shape=[n_samples,]
        """
        metric_det = gs.polygamma(1, param_a) * gs.polygamma(1, param_b) - \
            gs.polygamma(1, param_a + param_b) * (gs.polygamma(1, param_a) +
                                                  gs.polygamma(1, param_b))
        return metric_det

    def inner_product_matrix(self, base_point=None):
        """Compute inner product matrix at the tangent space at base point.

        Parameters
        ----------
        base_point : array-like, shape=[n_samples, 2]

        Returns
        -------
        base_point : array-like, shape=[n_samples, 2, 2]
        """
        if base_point is None:
            raise ValueError('The metric depends on the base point.')
        param_a = base_point[..., 0]
        param_b = base_point[..., 1]
        polygamma_ab = gs.polygamma(1, param_a + param_b)
        polygamma_a = gs.polygamma(1, param_a)
        polygamma_b = gs.polygamma(1, param_b)
        vector = gs.stack(
            [polygamma_a - polygamma_ab,
             - polygamma_ab,
             polygamma_b - polygamma_ab], axis=-1)
        return SymmetricMatrices.symmetric_matrix_from_vector(vector)

    def christoffels(self, base_point):
        """Compute the Christoffel symbols.

        Compute the Christoffel symbols of the Fisher information metric on
        Beta.

        Parameters
        ----------
        base_point : array-like, shape=[n_samples, 2]

        Returns
        -------
        christoffels : array-like, shape=[n_samples, 2, 2, 2]
        """
        def coefficients(param_a, param_b):
            metric_det = 2 * self.metric_det(param_a, param_b)
            poly_2_ab = gs.polygamma(2, param_a + param_b)
            poly_1_ab = gs.polygamma(1, param_a + param_b)
            poly_1_b = gs.polygamma(1, param_b)
            c1 = (gs.polygamma(2, param_a) *
                  (poly_1_b - poly_1_ab) - poly_1_b * poly_2_ab) / metric_det
            c2 = - poly_1_b * poly_2_ab / metric_det
            c3 = (gs.polygamma(2, param_b) * poly_1_ab - poly_1_b *
                  poly_2_ab) / metric_det
            return c1, c2, c3

        if base_point is None:
            raise ValueError('Christoffels require a base point.')
        point_a, point_b = base_point[..., 0], base_point[..., 1]
        c4, c5, c6 = coefficients(point_b, point_a)
        vector_0 = gs.stack(coefficients(point_a, point_b), axis=-1)
        vector_1 = gs.stack([c6, c5, c4], axis=-1)
        gamma_0 = SymmetricMatrices.symmetric_matrix_from_vector(vector_0)
        gamma_1 = SymmetricMatrices.symmetric_matrix_from_vector(vector_1)
        return gs.stack([gamma_0, gamma_1], axis=-3)

    def exp(self, tangent_vec, base_point, n_steps=N_STEPS):
        """Exponential map associated to the Fisher information metric.

        Exponential map at base_point of tangent_vec computed by integration
        of the geodesic equation (initial value problem), using the
        christoffel symbols.

        Parameters
        ----------
        tangent_vec : array-like, shape=[n_samples, dim]
        base_point : array-like, shape=[n_samples, dim]
        n_steps : int

        Returns
        -------
        exp : array-like, shape=[n_samples, dim]
        """
        base_point = gs.to_ndarray(base_point, to_ndim=2)
        tangent_vec = gs.to_ndarray(tangent_vec, to_ndim=2)

        def ivp(state, _):
            """Reformat the initial value problem geodesic ODE."""
            position, velocity = state[:2], state[2:]
            eq = self.geodesic_equation(velocity=velocity, position=position)
            return gs.hstack([velocity, eq])

        times = gs.linspace(0, 1, n_steps + 1)
        exp = []
        for point, vec in zip(base_point, tangent_vec):
            initial_state = gs.hstack([point, vec])
            geodesic = odeint(
                ivp, initial_state, times, (), rtol=1e-6)
            exp.append(geodesic[-1, :2])
        return exp[0] if len(base_point) == 1 else gs.stack(exp)

    def log(self, point, base_point, n_steps=N_STEPS):
        """Compute logarithm map associated to the Fisher information metric.

        Solve the boundary value problem associated to the geodesic ordinary
        differential equation (ODE) using the Christoffel symbols.

        Parameters
        ----------
        point : array-like, shape=[n_samples, dim]
        base_point : array-like, shape=[n_samples, dim]
        n_steps : int

        Returns
        -------
        tangent_vec : array-like, shape=[n_samples, dim]
            the initial velocity of the geodesic starting at base_point and
            reaching point at time 1
        """
        stop_time = 1.
        t = gs.linspace(0, stop_time, n_steps)
        point = gs.to_ndarray(point, to_ndim=2)
        base_point = gs.to_ndarray(base_point, to_ndim=2)

        def initialize(end_point, start_point):
            a0, b0 = start_point
            a1, b1 = end_point
            lin_init = gs.zeros([2 * self.dim, n_steps])
            lin_init[0, :] = gs.linspace(a0, a1, n_steps)
            lin_init[1, :] = gs.linspace(b0, b1, n_steps)
            lin_init[2, :-1] = (lin_init[0, 1:] - lin_init[0, :-1]) * n_steps
            lin_init[3, :-1] = (lin_init[1, 1:] - lin_init[1, :-1]) * n_steps
            lin_init[2, -1] = lin_init[2, -2]
            lin_init[3, -1] = lin_init[3, -2]
            return lin_init

        def bvp(_, state):
            """Reformat the boundary value problem geodesic ODE.

            Parameters
            ----------
            state :  array-like, shape[4,]
                Vector of the state variables: y = [a,b,u,v]
            _ :  unused
                Any (time).
            """
            position, velocity = state[:2].T, state[2:].T
            eq = self.geodesic_equation(
                velocity=velocity, position=position)
            return gs.vstack((velocity.T, eq.T))

        def boundary_cond(
                state_a, state_b, point_0_a, point_0_b, point_1_a, point_1_b):
            return gs.array(
                [state_a[0] - point_0_a,
                 state_a[1] - point_0_b,
                 state_b[0] - point_1_a,
                 state_b[1] - point_1_b])

        log = []
        for bp, pt in zip(base_point, point):
            geodesic_init = initialize(pt, bp)
            base_point_a, base_point_b = bp
            point_a, point_b = pt

            def bc(y0, y1):
                return boundary_cond(
                    y0, y1, base_point_a, base_point_b, point_a, point_b)

            solution = solve_bvp(bvp, bc, t, geodesic_init)
            geodesic = solution.sol(t)
            geodesic = geodesic[:2, :]
            log.append(n_steps * (geodesic[:, 1] - geodesic[:, 0]))

        return log[0] if len(base_point) == 1 else gs.stack(log)
