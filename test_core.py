"""Regression checks: run `python -m pytest -q test_core.py`."""
import json
import re
import numpy as np
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from point_core import (analyze, random_pattern, render_points, extract_dots, save_points_csv,
                        load_points_data, make_hopkins_probes, fast_score,
                        image_skeleton, evenly_sample_strokes, optimize_pattern, canvas_size,
                        ripley_multiscale, ripley_l_curve, csr_l_envelope, l_curve_radii,
                        l_curve_for_plot, l_axis_limit, l_curve_summary,
                        PATTERN_LABELS, PATTERN_LABELS_EN, HYBRID_KINDS)
from plots import l_plot_png, save_l_curves_csv, l_analysis, plot_title
from presets import PRESETS, make_preset, preset_label
from scipy.spatial import cKDTree


def test_score_directions():
    rng=np.random.default_rng(55)
    random,_=random_pattern(180,'random',rng=rng)
    cluster,_=random_pattern(180,'cluster',.9,rng)
    regular,_=random_pattern(180,'regular',.99,rng)
    a=analyze(random);b=analyze(cluster);c=analyze(regular)
    assert -1<=a['score']<=1
    assert b['score'] < a['score'] < c['score']
    assert b['score'] < -.6 and c['score'] > .6
    assert len([k for k in a if k.startswith('pair_g_')])==5
    assert len([k for k in a if k.startswith('ripley_l_minus_r_')])==5
    for axis in ('x','y'):
        assert np.isclose(a[f'{axis}_std']**2,a[f'{axis}_var'])


def test_score_does_not_depend_on_point_order():
    # v1.0 sampled Hopkins points by index: shuffling moved the score by up to ~0.1.
    rng=np.random.default_rng(3)
    for kind in ('random','cluster','regular'):
        p,_=random_pattern(180,kind,.6,rng)
        base=analyze(p)['score']
        for _ in range(3):
            assert analyze(p[rng.permutation(len(p))])['score']==pytest.approx(base,abs=1e-12)


def test_probe_layout_barely_matters():
    rng=np.random.default_rng(4)
    d=[analyze(p,seed=99)['score']-analyze(p)['score']
       for p in (random_pattern(180,'surprise',None,rng)[0] for _ in range(20))]
    assert np.max(np.abs(d)) < .02


def test_image_csv_roundtrip(tmp_path):
    pts=np.array([[.1,.1],[.45,.45],[.8,.2],[.3,.8]],float)
    image=tmp_path/'four.png'
    render_points(pts,image,(800,800),dot_radius=4)
    out,asp,meta=extract_dots(image,threshold=140,min_area=5)
    assert len(out)==4 and asp==1
    data=tmp_path/'xy.csv';save_points_csv(data,pts)
    recovered,asp2=load_points_data(data,1,1)
    np.testing.assert_allclose(recovered,pts,atol=1e-8)
    out_sorted=out[np.lexsort((out[:,1],out[:,0]))]
    pts_sorted=pts[np.lexsort((pts[:,1],pts[:,0]))]
    assert np.max(np.abs(out_sorted-pts_sorted))<.005


def test_png_and_csv_of_same_pattern_score_alike(tmp_path):
    p,_=random_pattern(120,'regular',.9,np.random.default_rng(8))
    render_points(p,tmp_path/'r.png',(1000,1000),3)
    q,asp,_=extract_dots(tmp_path/'r.png')
    assert len(q)==len(p)
    assert abs(analyze(q,asp)['score']-analyze(p)['score']) < .01


def test_json_pixel_coords(tmp_path):
    path=tmp_path/'points.json'
    path.write_text(json.dumps({'width':200,'height':100,
                                 'points':[[10,10],[100,50],[190,90]]}))
    p,aspect=load_points_data(path)
    assert aspect==2
    np.testing.assert_allclose(p[1],[.5,.5])


def test_quoted_csv_and_auto_bbox(tmp_path):
    path=tmp_path/'q.csv'
    path.write_text('"x","y"\n"10","20"\n"210","20"\n"110","120"\n',encoding='utf-8')
    p,aspect=load_points_data(path,1000,1000,auto_bbox=True)
    assert aspect==pytest.approx(2.0)          # bbox is 200 wide, 100 tall
    np.testing.assert_allclose(p,[[0,0],[1,0],[.5,1]])


def test_cluster_points_not_piled_on_border():
    rng=np.random.default_rng(5)
    for s in (.3,.6):
        p,_=random_pattern(400,'cluster',s,rng)
        assert np.mean((p==0)|(p==1)) == 0


def test_optimizer_and_reporting_same_score():
    p,_=random_pattern(75,'cluster',.8,np.random.default_rng(77))
    result=optimize_pattern(p,-.3,iterations=175,seed=11,stroke_xy=None)
    full=analyze(result['points'])
    assert np.isclose(full['score'],result['score'])
    assert -1<=result['score']<=1
    assert result['total_movement']>=0


def test_optimizer_zero_iterations():
    p,_=random_pattern(40,'cluster',.8,np.random.default_rng(1))
    r=optimize_pattern(p,.9,iterations=0)
    assert r['iterations']==0 and np.allclose(r['points'],p)


def test_skeleton_and_retention(tmp_path):
    im=Image.new('L',(320,320),'white')
    draw=ImageDraw.Draw(im)
    draw.ellipse((35,35,290,290),outline='black',width=4)
    path=tmp_path/'circle.png';im.save(path)
    skeleton,aspect,meta=image_skeleton(path)
    p=evenly_sample_strokes(skeleton,60,aspect)
    result=optimize_pattern(p,-.1,aspect,stroke_xy=skeleton,iterations=150,
          seed=12,max_stroke_distance=.04,min_stroke_retention=.75)
    assert len(result['points'])==60
    assert result['retained_within_025'] >= .75-1e-12
    assert result['points'].min()>=0 and result['points'].max()<=1


def test_transparent_png_line_art(tmp_path):
    # Black strokes on a fully transparent background (common for icons / clip art).
    im=Image.new('RGBA',(300,200),(0,0,0,0))
    ImageDraw.Draw(im).ellipse((40,30,260,170),outline=(0,0,0,255),width=4)
    path=tmp_path/'clear.png';im.save(path)
    skeleton,aspect,meta=image_skeleton(path)
    assert aspect==pytest.approx(1.5)
    assert meta['stroke_pixels'] < .1*300*200   # v1.0 treated the whole canvas as ink


def test_canvas_size_keeps_aspect():
    assert canvas_size(2.0,800)==(800,400)
    assert canvas_size(.5,800)==(400,800)


@pytest.mark.parametrize('label',list(PRESETS))
def test_every_preset_can_be_pointillized(tmp_path,label):
    path=make_preset(label,tmp_path/'p.png')
    skeleton,aspect,meta=image_skeleton(path)
    assert meta['skeleton_pixels'] > 800
    p=evenly_sample_strokes(skeleton,180,aspect)
    assert len(p)==180 and -1<=analyze(p,aspect)['score']<=1


def test_preset_lookup_by_key_or_label():
    assert preset_label('cat')=='小貓臉' and preset_label('小貓臉')=='小貓臉'
    assert preset_label('heart_arrow')=='一箭穿心'
    assert preset_label('nope') is None


# ---------------------------------------------------------------- L(r) and multi-scale types
def test_l_curve_uses_same_estimator_as_score():
    p,_=random_pattern(150,'cluster',.6,np.random.default_rng(1),1.5)
    rip=ripley_multiscale(p,1.5)
    c=ripley_l_curve(p,1.5,rip['radii'])
    np.testing.assert_allclose(c['l'],rip['l'],rtol=0,atol=1e-15)
    full=ripley_l_curve(p,1.5)
    assert full['r'][0]==0 and full['l'][0]==0
    assert full['r'][-1]==pytest.approx(.25)          # 1/4 of the short side


def test_l_curve_reads_the_right_way():
    rng=np.random.default_rng(2)
    r=l_curve_radii(180,1.)
    lo,hi=csr_l_envelope(180,1.,r)
    assert np.all(lo<=hi)
    csr=ripley_l_curve(rng.random((180,2)),1.,r)['l']
    assert np.mean((csr>=lo)&(csr<=hi)) > .8           # a random pattern stays in the band
    cl=ripley_l_curve(random_pattern(180,'cluster',.9,rng)[0],1.,r)['l']
    reg=ripley_l_curve(random_pattern(180,'regular',.95,rng)[0],1.,r)['l']
    mid=(r>.02)&(r<.06)
    assert np.all(cl[mid]>hi[mid]) and np.all(reg[mid]<lo[mid])


def test_envelope_is_cached_and_reproducible():
    r=l_curve_radii(90,2.)
    a=csr_l_envelope(90,2.,r); b=csr_l_envelope(90,2.,r.copy())
    assert a[0] is b[0]
    with pytest.raises(ValueError):
        a[0][0]=1.                                     # cached arrays are read-only


@pytest.mark.parametrize('kind',list(PATTERN_LABELS))
@pytest.mark.parametrize('aspect',[1.,2.,.5])
def test_every_pattern_type(kind,aspect):
    rng=np.random.default_rng(9)
    for n in (3,4,25,300):
        p,k=random_pattern(n,kind,.8,rng,aspect)
        assert k==kind and p.shape==(n,2) and p.min()>=0 and p.max()<=1
        assert len(np.unique(p,axis=0))==n


def test_multiscale_types_have_their_structure():
    rng=np.random.default_rng(10)
    n=200; spacing=np.sqrt(1/n)
    r=l_curve_radii(n,1.); lo,hi=csr_l_envelope(n,1.,r)
    def nn(p): return cKDTree(p).query(p,k=2)[0][:,1]
    def L(p): return ripley_l_curve(p,1.,r)['l']
    # hard-core everywhere: no two dots closer than ~0.6 spacing, yet no lattice
    p,_=random_pattern(n,'ms_regular_random',.8,rng)
    assert nn(p).min() > .55*spacing
    # tight clumps: far more close pairs than random at small r, back near the band at r=0.25
    for kind in ('ms_cluster_random','ms_cluster_regular'):
        l=L(random_pattern(n,kind,.8,rng)[0])
        assert l[8]>hi[8]
    # random_regular: equal counts on the coarse grid -> quadrat counts far below Poisson variance
    vmr=[analyze(random_pattern(n,'ms_random_regular',.8,rng)[0])['quadrat_vmr_4x4'] for _ in range(5)]
    assert np.mean(vmr) < .6
    # patches: points cover only part of the canvas
    for kind in ('ms_random_cluster','ms_regular_cluster'):
        p,_=random_pattern(n,kind,.8,rng)
        assert analyze(p)['quadrat_occupied_8x8'] < 50
    p,_=random_pattern(n,'ms_regular_cluster',.8,rng)
    assert nn(p).min() > .25*spacing


def test_hybrid_any_and_surprise_pick_concrete_types():
    rng=np.random.default_rng(11)
    seen={random_pattern(60,'hybrid_any',.7,rng)[1] for _ in range(120)}
    assert seen==set(HYBRID_KINDS)
    seen={random_pattern(60,'surprise',.7,rng)[1] for _ in range(200)}
    assert {'random','cluster','regular'} <= seen and seen <= set(PATTERN_LABELS)
    assert random_pattern(60,'小尺度群聚／大尺度均勻',.7,rng)[1]=='ms_cluster_regular'


def test_l_plot_png(tmp_path):
    p,_=random_pattern(120,'regular',.8,np.random.default_rng(3),2.)
    c,env,summary,data=l_analysis(p,2.,plot_title(PATTERN_LABELS_EN['regular'],.5),tmp_path/'l.png')
    assert data[:4]==bytes([137,80,78,71]) and (tmp_path/'l.png').read_bytes()==data
    im=Image.open(tmp_path/'l.png'); assert im.size[0]>500 and im.size[0]==im.size[1]
    assert summary['lr_regular_r']!='none'
    save_l_curves_csv(tmp_path/'c.csv',[('a',c,env),('b',c,None)])
    lines=(tmp_path/'c.csv').read_text(encoding='utf-8-sig').splitlines()
    assert lines[0]=='pattern,r,L,L_minus_r,K,csr_envelope_low,csr_envelope_high'
    assert len(lines)==2*len(c['r'])+1 and lines[-1].endswith(',,')


def test_square_axes_same_range():
    # Random / regular keep the usual 1/4-short-side range ...
    assert l_axis_limit(.25,.25)==(.25,.05) and l_axis_limit(.262,.25)==(.25,.05)
    # ... clustering widens both axes to the next round number above the curve.
    assert l_axis_limit(.38,.25)==(.40,.05) and l_axis_limit(.52,.25)==(.6,.1)
    assert l_axis_limit(.125,.125)==(.125,.025)
    rng=np.random.default_rng(6)
    for kind in ('random','regular','cluster','ms_random_cluster'):
        for aspect in (1.,2.,.5):
            p,_=random_pattern(180,kind,.8,rng,aspect)
            c=l_curve_for_plot(p,aspect)
            top=c['axis_max']
            assert c['r'][-1]==pytest.approx(min(top,.5*min(aspect,1)))
            inside=c['r']<=c['r_standard']+1e-12
            assert c['l'][inside].max()<=top*1.08+1e-12   # nothing in the usual range is cut off
            # same estimator as the score on the shared part of the grid
            ref=ripley_l_curve(p,aspect,c['r'])
            np.testing.assert_allclose(ref['l'],c['l'])


def test_l_curve_summary_reads_the_band():
    rng=np.random.default_rng(12)
    for kind,key in (('cluster','lr_clustered_r'),('ms_regular_random','lr_regular_r')):
        p,_=random_pattern(180,kind,.9,rng)
        c=l_curve_for_plot(p)
        s=l_curve_summary(c,csr_l_envelope(180,1.,c['r']))
        assert s[key]!='none' and re.match(r'\d\.\d{3}-\d\.\d{3}',s[key])
    p,_=random_pattern(180,'cluster',.9,rng)
    s=l_curve_summary(l_curve_for_plot(p))
    assert s['lr_max_L_minus_r']>0 and 'lr_clustered_r' not in s
