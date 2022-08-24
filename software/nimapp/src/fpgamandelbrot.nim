import nimgl/imgui, nimgl/imgui/[impl_opengl, impl_glfw]
import nimgl/[opengl, glfw]
import pkg/nint128
import fp128
import usb

const WIDTH        = 3840
const HEIGHT       = 2100
const RATIO        = 1 #3840 / 2100

const ARRAY_WIDTH  = 3000
const ARRAY_HEIGHT = (int)(ARRAY_WIDTH / RATIO)
var
    image {.align(128).}: array[0..(ARRAY_WIDTH * ARRAY_HEIGHT * 3), byte]
    colortable:           array[0..15, array[0..2, byte]]

colortable = [
    [ 66'u8,  30,  15],
    [ 25'u8,   7,  26],
    [  9'u8,   1,  47],
    [  4'u8,   4,  73],
    [  0'u8,   7, 100],
    [ 12'u8,  44, 138],
    [ 24'u8,  82, 177],
    [ 57'u8, 125, 209],
    [134'u8, 181, 229],
    [211'u8, 236, 248],
    [241'u8, 233, 191],
    [248'u8, 201,  95],
    [255'u8, 170,   0],
    [204'u8, 128,   0],
    [153'u8,  87,   0],
    [106'u8,  52,   3],
]

proc drawImage(width: int, height: int) =
    for x in 0..<width:
        for y in 0..<height:
            image[y * width * 3 + x * 3 + 0] = (byte)(x / 3)
            image[y * width * 3 + x * 3 + 1] = (byte)(y / 3)
            image[y * width * 3 + x * 3 + 2] = (byte)(x + y)

proc putPixel(x: int, y: int, val: byte) =
    image[y * ARRAY_WIDTH * 3 + x * 3 + 0 ] = val
    image[y * ARRAY_WIDTH * 3 + x * 3 + 1 ] = val
    image[y * ARRAY_WIDTH * 3 + x * 3 + 2 ] = val

proc clearImage(width: int, height: int) =
    for x in 0..<(width * height * 3):
        image[x] = 0

proc fixedpointnumber(data: ptr ImGuiInputTextCallbackData): int32 {.cdecl.} =
    let c = (char)data.eventChar
    if (('0' <= c and '9' >= c) or c == '-' or c == '.'):
        return 0

    return 1

proc fillWith(buf: ptr array[128, byte], s: string) =
    for i in 0..<len(s):
        buf[i] = (byte)s[i]

proc main() =
    doAssert glfwInit()

    glfwWindowHint(GLFWContextVersionMajor, 3)
    glfwWindowHint(GLFWContextVersionMinor, 3)
    glfwWindowHint(GLFWOpenglForwardCompat, GLFW_TRUE)
    glfwWindowHint(GLFWOpenglProfile, GLFW_OPENGL_CORE_PROFILE)
    glfwWindowHint(GLFWResizable, GLFW_FALSE)

    var w: GLFWWindow = glfwCreateWindow(WIDTH, HEIGHT)

    if w == nil:
        quit(-1)

    w.makeContextCurrent()

    doAssert glInit()

    let context = igCreateContext()

    doAssert igGlfwInitForOpenGL(w, true)
    doAssert igOpenGL3Init()

    igGetIO().fontGlobalScale = 2.5
    igStyleColorsCherry()

    glEnable(GL_TEXTURE_2D)
    glActiveTexture(GL_TEXTURE0)

    var tof: GLuint
    glGenTextures((GLsizei)1, addr tof)
    glBindTexture(GL_TEXTURE_2D, tof)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, (GLint)GL_CLAMP_TO_BORDER)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, (GLint)GL_CLAMP_TO_BORDER)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, (GLint)GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, (GLint)GL_LINEAR)

    #    glTexStorage2D(GL_TEXTURE_2D, (GLsizei)1, GL_RGB8, (GLsizei)WIDTH, (GLsizei)HEIGHT)
    #    glTexSubImage2D(GL_TEXTURE_2D, 1, 0, 0, WIDTH, HEIGHT, GL_RGB, GL_UNSIGNED_BYTE, addr image)

    var prevWidth:  int = 0
    var prevHeight: int = 0

    var
        center_x_buf: array[128, byte]
        center_y_buf: array[128, byte]
        radius_buf:   array[128, byte]
    let
        center_x_str = cast[cstring](addr center_x_buf[0])
        center_y_str = cast[cstring](addr center_y_buf[0])
        radius_str   = cast[cstring](addr radius_buf[0])

    (addr center_x_buf).fillWith("-0.75")
    (addr center_y_buf).fillWith("0")
    (addr radius_buf).fillWith("1.25")

    var
        center_x:  UInt128
        center_y:  UInt128
        radius:    UInt128
        corner_x:  UInt128
        corner_y:  UInt128

    while not w.windowShouldClose:
        glfwPollEvents()

        igOpenGL3NewFrame()
        igGlfwNewFrame()
        igNewFrame()

        # Simple window
        igBegin("FPGA Mandelbrot")
        igInputText("center x", center_x_str, (uint)len(center_x_buf), CallbackCharFilter, fixedpointnumber)
        igInputText("center y", center_y_str, (uint)len(center_y_buf), CallbackCharFilter, fixedpointnumber)
        igInputText("radius",   radius_str,   (uint)len(radius_buf),   CallbackCharFilter, fixedpointnumber)

        center_x = cast[UInt128](strToFp128($center_x_str))
        center_y = cast[UInt128](strToFp128($center_y_str))
        radius   = cast[UInt128](strToFp128($radius_str))

        # echo "radius: ", radius

        igText("  ")

        if igButton("Calculate", ImVec2(x: 0, y: 0)):
            let req = send_request(usb[0], 9, 1024, 1024, 0xaa, u128("0xfe0000000000000000"), u128("0xfeafe63d2eb11b6000"), u128("0x55deb9b1a4c35c"))
            var r = newSeq[byte](0)
            for response in req():
                r = r & @response
                while len(r) >= 6:
                    let x = (((uint)r[1]) shl 8) or (uint)r[0]
                    let y = (((uint)r[3]) shl 8) or (uint)r[2]
                    let p = r[4]
                    let s = r[5]
                    if s != 0xa5:
                        echo seq_hex(r[0..<6])
                        echo " ====> unexpected byte: ", s
                        r = r[6..r.high]
                        echo "rest: ", len(r)
                        continue

                    #echo $(x, y, p)
                    putPixel((int)x, (int)y, p)
                    r = r[6..r.high]

        igSameLine()

        igText(center_x_str)

        igText("Application average %.3f ms/frame (%.1f FPS)", 1000.0f / igGetIO().framerate, igGetIO().framerate)
        igEnd()

        #igShowMetricsWindow()

        glActiveTexture(GL_TEXTURE0)
        const inWindow = true
        if inWindow:
            igBegin("Fractal", nil, ImGuiWindowFlags.NoBringToFrontOnFocus)
            var width  = ((int)igGetWindowContentRegionWidth()) and not 0x3
            var height = ((int)igGetWindowHeight() - 50) and not 0x3

            if width != prevWidth or height != prevHeight:
                #clearImage(WIDTH, HEIGHT)
                #drawImage(width, height)
                prevWidth  = width
                prevHeight = height

            # TMP TMP TMP
            width = ARRAY_WIDTH
            height = ARRAY_HEIGHT

            glTexImage2D(GL_TEXTURE_2D, (GLint)0, (GLint)GL_RGB, (GLsizei)width, (GLsizei)height, (GLint)0, GL_RGB, GL_UNSIGNED_BYTE, addr image)
            igImage(cast[ImTextureID](tof), ImVec2(x: (float32)width, y: (float32)height))
            igEnd()
        else:
            glActiveTexture(GL_TEXTURE0)
            glTexImage2D(GL_TEXTURE_2D, (GLint)0, (GLint)GL_RGB, (GLsizei)WIDTH, (GLsizei)HEIGHT, (GLint)0, GL_RGB, GL_UNSIGNED_BYTE, addr image)
            var draw = igGetBackgroundDrawList()
            draw.addImage(cast[ImTextureID](tof), ImVec2(x: 0, y: 0), ImVec2(x: WIDTH, y: HEIGHT))

        igRender()

        glClearColor(0.45f, 0.55f, 0.60f, 1.00f)
        glClear(GL_COLOR_BUFFER_BIT)

        igOpenGL3RenderDrawData(igGetDrawData())

        w.swapBuffers()

    igOpenGL3Shutdown()
    igGlfwShutdown()
    context.igDestroyContext()

    w.destroyWindow()
    glfwTerminate()

main()
