# MeiWatermark

<p align="center">
  <img src="docs/assets/MeiWatermarkLogo.png" alt="MeiWatermark" width="280">
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <a href="README.en.md">English</a> · <strong>Español</strong> · <a href="README.ja.md">日本語</a>
</p>

MeiWatermark es una herramienta portátil y local para aplicar marcas de agua por lotes a imágenes en Windows; admite marcas de agua de imagen, texto y mosaico, múltiples capas y exportación por lotes.

Permite superponer y ordenar marcas de agua de imagen y texto, con posicionamiento por cuadrícula de nueve puntos, márgenes internos, opacidad, rotación, contornos de texto y ajustes preestablecidos reutilizables.

Exporta lotes en JPEG, PNG y WebP con control de calidad, restricciones de tamaño, estimaciones del tamaño de archivo y rutas de salida relativas.

## Funciones

- **Marcas de agua multicapa**: combine varias capas de imagen y texto; active, ordene y arrastre las capas.
- **Resultado visual coherente**: defina el tamaño por porcentaje del lado corto o píxeles; en las marcas de texto, el tamaño corresponde al lado mayor del texto renderizado, no al tamaño de fuente.
- **Posicionamiento preciso**: controle el anclaje de nueve puntos, los márgenes horizontal y vertical, la opacidad y la rotación. Los márgenes pueden ser negativos.
- **Marcas de texto**: use la lista de fuentes del sistema con nombres localizados; configure por separado el color del texto y del contorno, incluso sin color, y el grosor del contorno.
- **Marcas en mosaico**: cree marcas repetidas de texto o imagen en toda la foto, con espacio en porcentaje del lado corto y disposición alternada.
- **Vista previa en tiempo real**: arrastre imágenes a cualquier zona de la ventana; la vista actual permanece visible mientras se carga la siguiente foto, y la última imagen añadida se seleccionará y mostrará automáticamente.
- **Protecciones de renderizado**: los tamaños en píxeles superiores a 4096 px se ajustan a 4096; las marcas porcentuales cuyo tamaño renderizado o cantidad de mosaicos supere el límite se notifican y se omiten para esa imagen.
- **Gestión de fotos**: use `Delete`, el menú contextual o **Vaciar lista** para quitar fotos de la lista actual. Los archivos originales nunca se eliminan.
- **Exportación por lotes**: JPEG, PNG y WebP; calidad predeterminada de 100 y límites opcionales por lado largo, lado corto o escala.
- **Control de salida**: estima el tamaño del archivo de la imagen actual antes de exportar; permite conservar EXIF y perfiles ICC; admite rutas relativas a cada imagen original.
- **Gestión de preajustes**: cada preajuste guarda las capas y la configuración de exportación en un archivo JSON independiente.
- **Procesamiento local**: la lectura, vista previa y exportación se realizan localmente, sin servicios en la nube.
- **Interfaz multilingüe**: chino simplificado, inglés, español y japonés.

## Uso rápido

1. Seleccione **Abrir** o arrastre una o varias imágenes a cualquier zona de la ventana.
2. Añada una marca de imagen, texto o mosaico y ordene las capas en la lista.
3. Seleccione una capa y ajuste tamaño, margen, opacidad, rotación y anclaje de nueve puntos.
4. Elija formato, calidad, límite opcional de tamaño y destino de salida.
5. Seleccione **Exportar** para procesar el lote.

## Escala y posicionamiento

La **Proporción visual** basa el margen en el lado corto de la imagen, para conservar márgenes percibidos similares en imágenes horizontales y verticales. El **Porcentaje** de los márgenes usa el ancho o alto correspondiente; **px** está pensado para requisitos de píxeles fijos.

Para el tamaño de la marca, **%** usa el lado corto de la imagen. En las marcas de texto, controla el lado mayor del texto renderizado completo, de modo que una frase más larga conserve la proporción visual prevista.

Para la mayoría de trabajos fotográficos, use **%** para el tamaño de la marca de agua y **Proporción visual** para los márgenes.

Las marcas en mosaico usan los mismos controles de tamaño, opacidad y rotación, pero se repiten en toda la imagen. Su espacio usa el porcentaje del lado corto; no usan márgenes ni anclaje de nueve puntos.

## Preajustes y rutas de salida

Los preajustes guardan capas y configuración de exportación. La carpeta predeterminada es:

```text
%LOCALAPPDATA%\MeiWatermark\
```

Cada preajuste es un archivo `.json` independiente. El botón **Gestionar** abre esta carpeta; al guardar un nombre existente, se solicita confirmación antes de sobrescribirlo.

Deje vacía la ruta de salida para elegir un destino antes de exportar. Una ruta relativa como `/Mei` crea el destino junto a cada imagen original.

## Requisitos

- Windows 10 o posterior
- Python 3.12 (solo para ejecutar desde el código fuente)

La versión publicada es un ejecutable independiente de Windows y no requiere instalar Python.

## Ejecutar desde el código fuente

```powershell
conda create -n meiwatermark python=3.12 -y
conda activate meiwatermark
python -m pip install -e .
python -m meiwatermark
```

## Desarrollo y empaquetado

```powershell
# Ejecutar pruebas
python -m unittest discover -s tests -v

# Crear el ejecutable de Windows
python -m PyInstaller --noconfirm MeiWatermark.spec
```

La referencia de textos de la interfaz se mantiene en [docs/language-reference.md](docs/language-reference.md). Actualícela, junto con todos los idiomas incluidos, cuando cambie algún texto de la interfaz.

## Licencia

Este proyecto se distribuye bajo la [GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later).

Copyright © 2026 MeiStingray, Kicity Studio
<https://www.kicity.com>
