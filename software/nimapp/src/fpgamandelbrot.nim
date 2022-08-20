import nimgl/imgui, nimgl/imgui/[impl_opengl, impl_glfw]
import nimgl/[opengl, glfw]
import strformat# Copyright 2018, NimGL contributors.

const WIDTH        = 3840
const HEIGHT       = 2100
const RATIO        = 3840 / 2100

const ARRAY_WIDTH  = 6000
const ARRAY_HEIGHT = (int)(ARRAY_WIDTH / RATIO)
var image {.align(128).}: array[0..(ARRAY_WIDTH * ARRAY_HEIGHT * 3), byte]

proc drawImage(width: int, height: int) =
    for x in 0..<width:
        for y in 0..<height:
            image[y * width * 3 + x * 3 + 0] = (byte)(x / 3)
            image[y * width * 3 + x * 3 + 1] = (byte)(y / 3)
            image[y * width * 3 + x * 3 + 2] = (byte)(x + y)

proc clearImage(width: int, height: int) =
    for x in 0..<(width * height * 3):
        image[x] = 0

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

    var somefloat: float32 = 0.0f
    var counter: int32 = 0

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

    while not w.windowShouldClose:
        glfwPollEvents()

        igOpenGL3NewFrame()
        igGlfwNewFrame()
        igNewFrame()

        # Simple window
        igBegin("FPGA Mandelbrot")

        igText("This is some useful text.")

        igSliderFloat("float", somefloat.addr, 0.0f, 1.0f)

        if igButton("Button", ImVec2(x: 0, y: 0)):
            counter.inc
        igSameLine()
        igText("counter = %d", counter)

        igText("Application average %.3f ms/frame (%.1f FPS)", 1000.0f / igGetIO().framerate, igGetIO().framerate)
        igEnd()

        #igShowMetricsWindow()

        glActiveTexture(GL_TEXTURE0)
        const inWindow = true
        if inWindow:
            igBegin("Fractal", nil, NoBringToFrontOnFocus)
            var width  = ((int)igGetWindowContentRegionWidth()) and not 0x3
            var height = ((int)igGetWindowHeight() - 50) and not 0x3

            if width != prevWidth or height != prevHeight:
                clearImage(WIDTH, HEIGHT)
                drawImage(width, height)
                prevWidth  = width
                prevHeight = height

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
