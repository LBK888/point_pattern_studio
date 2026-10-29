"""Optional headless command line for repeatable tests and production batches."""
from pathlib import Path
import argparse
import json
import numpy as np
from point_core import (analyze, random_pattern, save_metrics_csv, save_points_csv,
    render_points, extract_dots, load_points_data, image_skeleton,
    evenly_sample_strokes, optimize_pattern, canvas_size, PATTERN_LABELS, PATTERN_LABELS_EN)
from plots import l_analysis, plot_title, save_l_curves_csv
from presets import PRESETS, make_preset, preset_label, preset_filename

IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')


def main():
    parser=argparse.ArgumentParser(description='Point Pattern Studio (non-GUI)')
    sub=parser.add_subparsers(dest='command',required=True)
    g=sub.add_parser('generate',help='Generate N dot images')
    g.add_argument('--count',type=int,default=5)
    g.add_argument('--points',type=int,default=180)
    g.add_argument('--mode',choices=[*PATTERN_LABELS,'hybrid_any','surprise'],default='surprise',
                   help='hybrid_any = one of the hybrid/ms_* types at random; ms_<small>_<large> = multi-scale types')
    g.add_argument('--strength',type=float,default=.8)
    g.add_argument('--seed',type=int,default=2026)
    g.add_argument('--width',type=int,default=800)
    g.add_argument('--height',type=int,default=800)
    g.add_argument('--out',default='output/cli_batch')
    a=sub.add_parser('analyze',help='Analyze image or CSV/TXT/JSON')
    a.add_argument('file')
    a.add_argument('--width',type=float,default=800)
    a.add_argument('--height',type=float,default=800)
    a.add_argument('--threshold',type=int,default=140)
    a.add_argument('--min-area',type=int,default=5)
    a.add_argument('--invert',action='store_true',help='White dots on black background')
    a.add_argument('--auto-bbox',action='store_true',help='Rescale data to its own bounding box (changes the score)')
    a.add_argument('--out',default='output/cli_import')
    o=sub.add_parser('optimize',help='Pointillize input strokes with a target score')
    o.add_argument('image',help='line-art image path, or a built-in preset name (see: python cli.py presets)')
    o.add_argument('--points',type=int,default=180)
    o.add_argument('--target',type=float,default=-.13)
    o.add_argument('--iterations',type=int,default=3000)
    o.add_argument('--tolerance',type=float,default=.035)
    o.add_argument('--max-off-stroke',type=float,default=.09)
    o.add_argument('--free',action='store_true',help='Do not constrain per-point distance to original stroke')
    o.add_argument('--min-retention',type=float,default=.65,help='Min fraction of points within 0.025 of original strokes')
    o.add_argument('--seed',type=int,default=2026)
    o.add_argument('--threshold',type=int,default=150)
    o.add_argument('--invert',action='store_true',help='White lines on black background')
    o.add_argument('--out',default='output/cli_optimize')
    pr=sub.add_parser('presets',help='List built-in line-art presets; with --out, save them as PNG')
    pr.add_argument('--out',default=None)
    args=parser.parse_args()

    if args.command=='presets':
        for label,(key,_) in PRESETS.items():
            print(f'{key:12s} {label}')
        if args.out:
            for label in PRESETS:
                make_preset(label,Path(args.out)/preset_filename(label))
            print('Saved to',Path(args.out).resolve())
        return

    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if args.command=='generate':
        rng=np.random.default_rng(args.seed)
        rows=[];curves=[]
        aspect=args.width/args.height
        for i in range(args.count):
            p, typ=random_pattern(args.points,args.mode,args.strength,rng,aspect)
            row=analyze(p,aspect)
            row.update(id=i+1,kind=typ,label=PATTERN_LABELS[typ])
            rows.append(row)
            name=f'pattern_{i+1:04d}'
            render_points(p,out/f'{name}.png',(args.width,args.height))
            save_points_csv(out/f'{name}_xy.csv',p)
            curve,envelope,summary,_=l_analysis(p,aspect,plot_title(PATTERN_LABELS_EN[typ],row['score']),
                                                out/f'{name}_Lr.png')
            curves.append((name,curve,envelope)); row.update(summary)
            print(f'{i+1}: {typ}, score={row["score"]:+.4f}')
        save_metrics_csv(out/'all_metrics.csv',rows)
        save_l_curves_csv(out/'Lr_curves.csv',curves)
    elif args.command=='analyze':
        if Path(args.file).suffix.lower() in IMAGE_EXT:
            p,aspect,meta=extract_dots(args.file,args.threshold,args.min_area,args.invert)
        else:
            p,aspect=load_points_data(args.file,args.width,args.height,args.auto_bbox)
        row=analyze(p,aspect)
        curve,envelope,summary,_=l_analysis(p,aspect,plot_title(Path(args.file).name,row['score']),out/'Lr.png')
        row.update(summary)
        print(json.dumps(row,ensure_ascii=False,indent=2))
        save_points_csv(out/'xy.csv',p)
        save_metrics_csv(out/'metrics.csv',[row])
        save_l_curves_csv(out/'Lr_curve.csv',[(Path(args.file).name,curve,envelope)])
    else:
        if not (-1<=args.target<=1):parser.error('--target must be in [-1,1]')
        image=Path(args.image)
        if not image.is_file():
            label=preset_label(args.image)
            if label is None:
                parser.error(f'找不到圖片，也不是內建圖形名稱：{args.image}（python cli.py presets 可列出名稱）')
            image=make_preset(label,out/preset_filename(label))
            print('Preset:',label,'->',image)
        stroke,aspect,meta=image_skeleton(image,args.threshold,args.invert)
        p=evenly_sample_strokes(stroke,args.points,aspect,args.seed)
        before=analyze(p,aspect)
        result=optimize_pattern(p,args.target,aspect,stroke,iterations=args.iterations,
             tolerance=args.tolerance, max_stroke_distance=None if args.free else args.max_off_stroke,
             min_stroke_retention=args.min_retention, seed=args.seed, progress=lambda i,n,s,r: print(f'{i}/{n}: {s:+.4f}',flush=True) if i==n else None)
        after=analyze(result['points'],aspect)
        print(f'Before={before["score"]:+.4f}, After={after["score"]:+.4f}, Target={args.target:+.4f}, '
              f'Hit={abs(after["score"]-args.target)<=args.tolerance}, Retained={result["retained_within_025"]:.1%}')
        save_points_csv(out/'before_xy.csv',p)
        save_points_csv(out/'optimized_xy.csv',result['points'])
        save_metrics_csv(out/'before_after_metrics.csv',[{'phase':'before',**before},{'phase':'after',**after}])
        size=canvas_size(aspect)
        render_points(p,out/'before.png',size)
        render_points(result['points'],out/'after.png',size)
        meta={key:val for key,val in result.items() if key!='points'}
        (out/'optimization.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Output:',out.resolve())


if __name__=='__main__':main()
