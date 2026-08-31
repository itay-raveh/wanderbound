from app.logic.pdf import render_capacity, render_timeouts


def test_pdf_rendering_scales_down_for_constrained_cpus() -> None:
    one_cpu = render_timeouts(1)
    two_cpus = render_timeouts(2)
    four_cpus = render_timeouts(4)

    assert one_cpu[0] > two_cpus[0] > four_cpus[0]
    assert one_cpu[1] > two_cpus[1] > four_cpus[1]
    assert all(render > page for page, render in (one_cpu, two_cpus, four_cpus))
    assert render_capacity(1) == render_capacity(2) == 1
    assert render_capacity(4) > render_capacity(2)
