from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
import xml.sax.saxutils as saxutils

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT_DIR = ROOT / "report_output"
OUT_DIR.mkdir(exist_ok=True)

DOCX_PATH = OUT_DIR / "practica5kurs_report_detailed_v3.docx"
FIG_PATH = OUT_DIR / "figure_1_architecture.png"


@dataclass
class FileInfo:
    name: str
    purpose: str
    classes_funcs: str
    io_data: str
    algorithms: str


def get_code_files() -> list[Path]:
    return [SRC / name for name in ("main.py", "scene_view.py", "camera_view.py", "camera_math.py", "gcode_parser.py")]


def build_architecture_figure(path: Path) -> None:
    img = Image.new("RGB", (1800, 1000), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
        font_bold = ImageFont.truetype("arialbd.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    def box(x1, y1, x2, y2, title, body):
        draw.rounded_rectangle((x1, y1, x2, y2), radius=24, outline="black", width=4, fill=(245, 248, 252))
        draw.text((x1 + 20, y1 + 16), title, fill="black", font=font_bold)
        draw.multiline_text((x1 + 20, y1 + 70), body, fill="black", font=font, spacing=8)

    box(70, 90, 380, 250, "main.py", "Запуск приложения\nАргументы пути\nСохранение JSON")
    box(70, 350, 380, 540, "scene_view.py", "3D сцена\nOrbitCamera\nVBO отрисовка")
    box(70, 650, 380, 840, "camera_view.py", "Фото + проекция\nМаска модели\nBBox для MobileSAM")

    box(580, 180, 940, 340, "camera_math.py", "Матрицы\nПроекции\nОбщая математика камеры")
    box(580, 560, 940, 720, "gcode_parser.py", "Парсинг G-code\nСлои и сегменты")

    box(1160, 250, 1710, 620, "Результаты и данные", "Фото из data/photo\nG-code из data/gcode\nКалибровки JSON\nБудущая интеграция MobileSAM")

    arrows = [
        ((380, 170), (580, 250)),
        ((380, 430), (580, 260)),
        ((380, 745), (1160, 410)),
        ((380, 140), (580, 620)),
        ((380, 430), (1160, 390)),
        ((940, 260), (1160, 360)),
        ((940, 640), (1160, 430)),
    ]
    for start, end in arrows:
        draw.line([start, end], fill="black", width=5)
        # arrow head
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        tip = end
        left = (end[0] - ux * 26 + px * 12, end[1] - uy * 26 + py * 12)
        right = (end[0] - ux * 26 - px * 12, end[1] - uy * 26 - py * 12)
        draw.polygon([tip, left, right], fill="black")

    draw.text((70, 25), "Архитектура проекта", fill="black", font=font_bold)
    img.save(path)


def esc(text: str) -> str:
    return saxutils.escape(text).replace("\n", "<w:br/>")


def make_p(text: str, bold: bool = False, center: bool = False, indent: bool = True, size: int = 28):
    jc = "center" if center else "both"
    first = ' w:firstLine="708"' if indent else ""
    rpr = f'<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b w:val="1"/><w:sz w:val="{size}"/></w:rPr>' if bold else f'<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="{size}"/></w:rPr>'
    return f'<w:p><w:pPr><w:jc w:val="{jc}"/><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLine="708"{"" if not indent else ""}/></w:pPr><w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>'


def make_heading(num: str, title: str, level: int = 1):
    text = f"{num} {title}"
    if level == 1:
        return make_p(text, bold=True, center=True, indent=False, size=32)
    return make_p(text, bold=True, center=False, indent=True, size=28)


def make_bullet(text: str):
    return f'<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLine="708"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="28"/></w:rPr><w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>'


def make_table(rows: list[list[str]], title: str, numbered: bool = True) -> str:
    cap = f"Table 1 {title}" if numbered else title
    tbl_rows = []
    for i, row in enumerate(rows):
        cells = []
        for cell in row:
            cells.append(
                "<w:tc><w:tcPr><w:tcW w:w='2400' w:type='dxa'/></w:tcPr>"
                f"<w:p><w:r><w:rPr><w:rFonts w:ascii='Times New Roman' w:hAnsi='Times New Roman'/><w:sz w:val='22'/></w:rPr><w:t xml:space='preserve'>{esc(cell)}</w:t></w:r></w:p>"
                "</w:tc>"
            )
        tbl_rows.append("<w:tr>" + "".join(cells) + "</w:tr>")
    return make_p(cap, bold=True, center=True, indent=False, size=24) + f"<w:tbl><w:tblPr><w:tblW w:w='0' w:type='auto'/></w:tblPr>{''.join(tbl_rows)}</w:tbl>"


def make_image(path: str, caption: str) -> str:
    return (
        f"<w:p><w:r><w:drawing><wp:inline xmlns:wp='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing' distT='0' distB='0' distL='0' distR='0'>"
        f"<wp:extent cx='15240000' cy='8460000'/><wp:docPr id='1' name='Picture 1'/>"
        f"<a:graphic xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:graphicData uri='http://schemas.openxmlformats.org/drawingml/2006/picture'>"
        f"<pic:pic xmlns:pic='http://schemas.openxmlformats.org/drawingml/2006/picture'>"
        f"<pic:nvPicPr><pic:cNvPr id='1' name='architecture'/><pic:cNvPicPr/></pic:nvPicPr>"
        f"<pic:blipFill><a:blip r:embed='rId1'/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        f"<pic:spPr><a:xfrm><a:off x='0' y='0'/><a:ext cx='15240000' cy='8460000'/></a:xfrm><a:prstGeom prst='rect'><a:avLst/></a:prstGeom></pic:spPr>"
        f"</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        + make_p(caption, center=True, indent=False, size=22)
    )


def build_docx(docx_path: Path, fig_path: Path, files: list[FileInfo]) -> None:
    p = []
    p.append(make_p("ОТЧЕТ ПО ПРОЕКТУ КАЛИБРОВКИ КАМЕРЫ ДЛЯ КОНТРОЛЯ 3D-ПЕЧАТИ", bold=True, center=True, indent=False, size=32))
    p.append(make_p("Проект practica5kurs/main_papka", center=True, indent=False, size=26))

    p.append(make_heading("1", "ВВЕДЕНИЕ"))
    p.append(make_p("Проект относится к области Additive Manufacturing (AM) и связан с визуальным контролем качества печати на 3D-принтере. Целью системы является сопоставление виртуальной модели, восстановленной по G-code, с реальным изображением детали, полученным с камеры. Такой подход позволяет оценивать соответствие геометрии, а в дальнейшем может быть расширен до контроля по слоям и привязки к физическим размерам." ))

    p.append(make_heading("2", "ЦЕЛЬ И ЗАДАЧИ"))
    p.append(make_p("Цель проекта — создать программную среду для калибровки камеры и дальнейшего сравнения виртуальной модели детали с фактическим изображением напечатанного объекта."))
    for t in [
        "считать G-code и восстановить из него 3D-представление траекторий печати;",
        "обеспечить интерактивный просмотр 3D-модели с управлением камерой;",
        "наложить проекцию виртуальной модели на фотографию объекта;",
        "сохранять параметры калибровки в JSON-файл;",
        "подготовить виртуальную маску модели для использования в MobileSAM.",
    ]:
        p.append(make_bullet(t))

    p.append(make_heading("3", "ОСНОВНАЯ ЧАСТЬ"))
    p.append(make_heading("3.1", "РЕАЛИЗАЦИЯ И ИТОГИ", level=2))
    p.append(make_p("В текущей версии реализованы два визуальных окна: 3D-вид сцены и окно наложения на фотографию. Параметры камеры синхронизируются между окнами, а итоговое состояние сохраняется в JSON. Для калибровки дополнительно реализованы прозрачность проекции и обводка, благодаря которым границы модели становятся лучше различимыми на фоне изображения." ))

    p.append(make_heading("3.1.1", "АРХИТЕКТУРА ПРОЕКТА", level=2))
    p.append(make_p("Общая архитектура проекта представлена на Figure 1. Центральным элементом выступает модуль main.py, который связывает парсер G-code, 3D-сцену, окно наложения и параметры калибровки."))
    p.append(make_image(str(fig_path), "Fig. 1 — General architecture of the calibration project."))
    p.append(make_p("Process overview is presented in Figure 1.", indent=True))

    p.append(make_heading("3.1.2", "ОПИСАНИЕ ФАЙЛОВ", level=2))
    p.append(make_p("Ниже приведено развернутое описание основных исполняемых модулей проекта. Для каждого файла показаны его место в общей архитектуре, характер данных, с которыми он работает, и то, как его функции влияют на построение виртуальной модели и дальнейшее сопоставление с фотографией детали."))

    for idx, f in enumerate(files, start=1):
        p.append(make_heading(f"3.1.2.{idx}", f.name.upper(), level=2))
        if f.name == "main.py":
            p.append(make_heading(f"3.1.2.{idx}.1", "Роль в системе", level=2))
            p.append(make_p("Модуль main.py задает общую композицию приложения и отвечает за сборку всех его основных частей. В нем формируется конфигурация запуска, создается главное окно, подключаются 3D-вид и окно наложения на фотографию, а также запускается цикл Qt-приложения. В системе калибровки именно этот модуль объединяет подготовку входных данных, интерфейс пользователя и сохранение результата работы."));
            p.append(make_heading(f"3.1.2.{idx}.2", "Организация данных", level=2))
            p.append(make_p("При старте программа получает пути к G-code, фотографии и JSON-файлу с параметрами калибровки. Эти значения собираются в объект AppConfig и далее передаются в окно приложения, которое распределяет их между визуальными компонентами. После этого main.py инициирует чтение слоев G-code и синхронизирует обе визуальные панели, чтобы камера и сцена работали с одним и тем же набором параметров."));
            p.append(make_heading(f"3.1.2.{idx}.3", "Ключевые элементы и алгоритмы", level=2))
            p.append(make_p("Внутри main.py используются AppConfig, функция parse_args(), класс MainWindow и точка входа main(). Их семантическая роль состоит не только в запуске программы, но и в поддержании единого состояния системы. Здесь же реализованы механизмы загрузки и сохранения калибровки, автоматическая инициализация сохраненного состояния и связка между обработкой G-code и визуальным контролем."));
            p.append(make_p("Таким образом, main.py отвечает за связность всех подсистем и обеспечивает воспроизводимость запуска за счет явной конфигурации входных и выходных путей."))
        elif f.name == "scene_view.py":
            p.append(make_heading(f"3.1.2.{idx}.1", "Роль в системе", level=2))
            p.append(make_p("Модуль scene_view.py отвечает за трехмерное представление виртуальной модели, восстановленной из G-code. Он используется тогда, когда оператору требуется не только увидеть траектории печати, но и вручную подстроить положение камеры относительно модели. Это делает модуль основным инструментом первичной визуальной подгонки перед наложением на фотографию."));
            p.append(make_heading(f"3.1.2.{idx}.2", "Организация данных", level=2))
            p.append(make_p("На вход scene_view.py поступают слои G-code, преобразованные в список сегментов. После загрузки модуль вычисляет геометрические характеристики модели, определяет ее центр и автоматически подстраивает дистанцию камеры. Дальше данные переводятся в буфер VBO, чтобы OpenGL мог отрисовывать модель эффективно и без повторного пересчета геометрии на каждом кадре."));
            p.append(make_heading(f"3.1.2.{idx}.3", "Ключевые элементы и алгоритмы", level=2))
            p.append(make_p("Содержательно модуль опирается на класс SceneView и объект OrbitCamera, который описывает орбитальное движение вокруг цели. Важной частью реализации является построение VBO в методе _create_vbo(), где все сегменты объединяются в один массив и передаются в графический буфер. Отдельно реализованы отрисовка осей, сетки, обработка мыши и масштабирование, что позволяет использовать окно не как статичную картинку, а как средство интерактивного выбора ракурса."));
            p.append(make_p("В итоге scene_view.py обеспечивает ту часть проекта, где оператор подбирает геометрию взгляда, необходимую для корректного совмещения виртуальной и реальной модели."))
        elif f.name == "camera_view.py":
            p.append(make_heading(f"3.1.2.{idx}.1", "Роль в системе", level=2))
            p.append(make_p("Модуль camera_view.py реализует вторую половину калибровочного сценария: он работает с фотографией реального объекта и накладывает на нее проекцию виртуальной модели. В отличие от 3D-окна, здесь важна не интерактивная геометрия сама по себе, а точность совмещения контуров, потому что именно по этому наложению оператор оценивает корректность калибровки."));
            p.append(make_heading(f"3.1.2.{idx}.2", "Организация данных", level=2))
            p.append(make_p("В модуль поступают путь к изображению, состояние камеры из scene_view.py и те же слои G-code, которые были восстановлены парсером. Сначала фото загружается и приводится к размерам рабочей области, затем через общую математику камеры вычисляется проекция сегментов в экранные координаты. На этой основе формируется наложение с регулируемой прозрачностью и дополнительной обводкой, а затем вычисляется маска виртуальной модели."));
            p.append(make_heading(f"3.1.2.{idx}.3", "Ключевые элементы и алгоритмы", level=2))
            p.append(make_p("Главный класс CameraView содержит набор методов, который связывает визуальное наложение с подготовкой данных для MobileSAM. Метод _view_projection() формирует матрицы вида и проекции, get_projected_bbox() оценивает охватывающий прямоугольник по экранным точкам, а get_virtual_model_mask() строит бинарную маску проекции в координатах изображения. Метод get_virtual_model_search_bbox() использует эту маску как ограничение области поиска для сегментации, что особенно важно в условиях, когда фон содержит лишние детали и отражения."));
            p.append(make_p("Таким образом, camera_view.py выполняет роль промежуточного звена между геометрией G-code и нейросетевой обработкой изображения, соединяя ручную калибровку и будущую автоматическую сегментацию."))
        elif f.name == "camera_math.py":
            p.append(make_heading(f"3.1.2.{idx}.1", "Роль в системе", level=2))
            p.append(make_p("Модуль camera_math.py задает общую математическую основу проекта. Он не отвечает за интерфейс или загрузку данных напрямую, но именно здесь сосредоточены все преобразования, без которых невозможно согласовать координаты G-code, 3D-сцены и изображения с камеры. В системе калибровки этот модуль обеспечивает единообразие геометрических вычислений."));
            p.append(make_heading(f"3.1.2.{idx}.2", "Организация данных", level=2))
            p.append(make_p("На вход функции и методы модуля принимают набор 3D-точек и параметры камеры. На выходе они формируют матрицы преобразований, экранные координаты и состояние камеры, пригодное для сохранения в JSON. Такой формат удобен тем, что одну и ту же структуру состояния можно применять и в интерактивном 3D-окне, и в окне наложения на фотографию."));
            p.append(make_heading(f"3.1.2.{idx}.3", "Ключевые элементы и алгоритмы", level=2))
            p.append(make_p("Основой модуля являются функции look_at() и perspective_projection(), которые строят матрицы вида и перспективной проекции. Дополняет их класс OrbitCamera, описывающий орбитальное движение камеры вокруг цели. Внутри класса реализованы методы rotate(), zoom() и pan(), а также вычисление позиции eye через сферические координаты. Эти процедуры позволяют согласованно менять ракурс и сохранять геометрию наблюдения при переходе между окнами."));
            p.append(make_p("camera_math.py играет стабилизирующую роль: именно благодаря нему все визуальные компоненты используют одинаковую систему преобразований и не расходятся по смыслу при сохранении и повторной загрузке калибровки."))
        elif f.name == "gcode_parser.py":
            p.append(make_heading(f"3.1.2.{idx}.1", "Роль в системе", level=2))
            p.append(make_p("Модуль gcode_parser.py отвечает за преобразование текстового G-code в структуру, с которой уже можно работать как с геометрией. В контексте проекта это исходный этап восстановления виртуальной модели детали, по которой затем строится 3D-представление и вычисляется проекция на фотографию."));
            p.append(make_heading(f"3.1.2.{idx}.2", "Организация данных", level=2))
            p.append(make_p("На вход парсер получает путь к файлу G-code. Внутри он последовательно читает строки, отбрасывает комментарии, выделяет команды перемещения и определяет, где происходит экструзия. Далее точки группируются по слоям Z, а travel-move используется как признак разрыва между сегментами. На выходе получается список слоев, каждый из которых представляет собой набор numpy-массивов с координатами траекторий."));
            p.append(make_heading(f"3.1.2.{idx}.3", "Ключевые элементы и алгоритмы", level=2))
            p.append(make_p("Функция parse_gcode_layers() реализует основную логику разбора. Она учитывает режим абсолютной и относительной экструзии, отслеживает изменение Z-координаты, а также отделяет печатающие участки от холостых перемещений по порогу расстояния TRAVEL_THRESHOLD. Такая схема дает достаточно компактное, но при этом информативное представление о послойной структуре печати."));
            p.append(make_p("Именно gcode_parser.py превращает текстовое описание печати в данные, пригодные для визуализации, калибровки и последующего сравнения с маской, полученной по фотографии."))

    p.append(make_heading("3.1.3", "СВЯЗИ МЕЖДУ ФАЙЛАМИ", level=2))
    inter_rows = [
        ["Источник", "Приемник", "Смысл связи"],
        ["main.py", "gcode_parser.py", "Парсинг G-code и получение слоев"],
        ["main.py", "scene_view.py", "Загрузка слоев в 3D-вид и синхронизация камеры"],
        ["main.py", "camera_view.py", "Загрузка слоев, фото и параметров калибровки"],
        ["scene_view.py", "camera_math.py", "Использование OrbitCamera и матриц преобразования"],
        ["camera_view.py", "camera_math.py", "Проекция 3D-точек в 2D и построение маски"],
    ]
    p.append(make_table(inter_rows, "Interconnections between files", numbered=True))
    p.append(make_p("Связи между модулями summarized in Table 2."))
    p.append(make_p("Связи между файлами организованы по принципу централизованного управления. main.py инициирует загрузку G-code и фотографии, затем передает данные в scene_view.py и camera_view.py. scene_view.py, в свою очередь, использует camera_math.py для вычисления положения камеры и преобразования координат. camera_view.py опирается на ту же математику, но применяет ее к 2D-картинке, чтобы отрисовать проекцию и построить маску виртуальной модели."))
    p.append(make_p("Такое разделение позволяет не смешивать вычисления, интерфейс и обработку исходных данных в одном файле. В дальнейшем это упростит подключение MobileSAM, потому что модуль сегментации можно будет встроить в уже подготовленный поток данных без существенной перестройки архитектуры."))

    p.append(make_heading("3.1.4", "ПЕРСПЕКТИВЫ ДАЛЬНЕЙШЕГО РАЗВИТИЯ", level=2))
    p.append(make_p("Следует отметить, что текущая версия проекта завершает только этап подготовки к калибровке, но еще не доводит его до полностью автоматизированного решения. На данном этапе уже реализованы восстановление виртуальной модели по G-code, интерактивная подстройка камеры, сохранение параметров в JSON и построение проекции на фотографию. Однако сам процесс калибровки еще нельзя считать завершенным, поскольку для устойчивого перехода к следующему этапу требуется формализовать сравнение виртуальной и реальной геометрии." ))
    p.append(make_p("В дальнейшем предполагается использовать параметры, сохраненные в JSON, для восстановления положения камеры и области поиска на изображении для каждого нового G-code. Иными словами, для каждой новой детали область интереса будет строиться индивидуально: известная геометрия, извлеченная из G-code, и параметры положения камеры, сохраненные после калибровки, позволят ограничить часть изображения, где действительно ожидается объект. Такой подход особенно важен при использовании MobileSAM, поскольку без задания области поиска модель сегментирует все содержимое кадра, а не только нужную деталь." ))
    p.append(make_p("На следующем этапе требуется завершить именно процедуру калибровки, то есть добиться устойчивого совпадения виртуальной модели и наблюдаемого объекта. После этого можно будет добавить алгоритм сравнения масок или контуров, который в дальнейшем пригодится и для геометрического контроля. В практическом смысле этот алгоритм должен оценивать степень совпадения формы, фиксировать расхождения по границе и формировать числовую характеристику качества совмещения." ))
    p.append(make_p("Таким образом, текущая версия проекта представляет собой неполную реализацию калибровочного этапа. Она уже содержит необходимую геометрическую и программную основу, но дальнейшее развитие связано с завершением калибровки, вычислением области поиска по JSON-параметрам и последующим внедрением алгоритма сравнения как для работы с MobileSAM, так и для контроля формы детали."))

    p.append(make_heading("4", "ЗАКЛЮЧЕНИЕ"))
    p.append(make_p("Проект уже содержит рабочую основу для калибровки камеры и визуального сопоставления виртуальной и физической модели. Главный практический результат состоит в том, что мы получили управляемую 3D-сцену, наложение на фотографию, сохранение параметров калибровки и инструментальную маску виртуальной модели, которую можно использовать как стартовую область поиска для MobileSAM. Следующий этап логично связать с автоматическим сравнением масок и оценкой отклонений по слоям." ))

    document_body = "".join(p)
    return document_body


def build_package(docx_path: Path, fig_path: Path, body_xml: str):
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/figure_1_architecture.png"/>
</Relationships>"""

    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>
      <w:sz w:val="28"/>
    </w:rPr>
  </w:style>
</w:styles>"""

    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    {body_xml}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="567" w:bottom="1134" w:left="1701" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/styles.xml", styles)
        zf.write(fig_path, "word/media/figure_1_architecture.png")


def main():
    build_architecture_figure(FIG_PATH)

    files = [
        FileInfo(
            name="main.py",
            purpose="Точка входа приложения. Собирает интерфейс, конфигурацию запуска и синхронизацию между окнами.",
            classes_funcs="AppConfig, parse_args(), MainWindow, main()",
            io_data="Вход: пути к G-code, фото и JSON; выход: окно приложения, параметры калибровки в JSON.",
            algorithms="Парсинг аргументов, загрузка слоев, автозагрузка калибровки, синхронизация состояния камеры.",
        ),
        FileInfo(
            name="scene_view.py",
            purpose="3D-визуализатор виртуальной модели по G-code.",
            classes_funcs="SceneView, load_layers(), get_camera_state(), set_camera_state(), _draw_gcode_vbo()",
            io_data="Вход: слои G-code; выход: OpenGL-сцена и состояние камеры.",
            algorithms="Построение VBO, орбитальная камера, автоподгонка центра модели, отрисовка сетки и осей.",
        ),
        FileInfo(
            name="camera_view.py",
            purpose="Наложение виртуальной модели на фото для калибровки и подготовки данных для MobileSAM.",
            classes_funcs="CameraView, get_projected_bbox(), get_virtual_model_mask(), get_virtual_model_search_bbox()",
            io_data="Вход: изображение, слои G-code, состояние камеры; выход: изображение с проекцией, bbox, бинарная маска.",
            algorithms="Проекция 3D-точек в 2D, построение бинарной маски, поиск bbox по маске, отрисовка с прозрачностью и обводкой.",
        ),
        FileInfo(
            name="camera_math.py",
            purpose="Общая математика камеры и геометрических преобразований.",
            classes_funcs="OrbitCamera, look_at(), perspective_projection(), world_to_screen()",
            io_data="Вход: 3D-координаты и параметры камеры; выход: матрицы и экранные координаты.",
            algorithms="Построение view/projection матриц, spherical orbit camera, перевод из мировых координат в экранные.",
        ),
        FileInfo(
            name="gcode_parser.py",
            purpose="Парсинг G-code и восстановление слоев траекторий печати.",
            classes_funcs="parse_gcode_layers(), TRAVEL_THRESHOLD",
            io_data="Вход: файл G-code; выход: список слоев и сегментов в виде numpy-массивов.",
            algorithms="Выделение extrusion moves, группировка по Z, разбиение по travel-move, фильтрация слоев.",
        ),
    ]
    body = build_docx(DOCX_PATH, FIG_PATH, files)
    build_package(DOCX_PATH, FIG_PATH, body)
    print(DOCX_PATH)


if __name__ == "__main__":
    main()
