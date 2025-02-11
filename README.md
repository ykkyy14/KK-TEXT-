# KK-TEXT-
KK TEXT  主要用于学习  和练习
[tetris.html.txt](https://github.com/user-attachments/files/18752267/tetris.html.txt)
<!DOCTYPE html>
<html>
<head>
    <title>俄罗斯方块</title>
    <style>
        body {
            background: #202028;
            color: #fff;
            font-family: sans-serif;
            font-size: 2em;
            text-align: center;
        }
        canvas {
            border: 2px solid #fff;
        }
        .container {
            display: flex;
            justify-content: center;
            gap: 50px;
            margin-top: 20px;
        }
        .info {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <canvas id="board" width="300" height="600"></canvas>
        <div class="info">
            <div>得分: <span id="score">0</span></div>
            <div>下一个:</div>
            <canvas id="next" width="120" height="120"></canvas>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('board');
        const ctx = canvas.getContext('2d');
        const nextCanvas = document.getElementById('next');
        const nctx = nextCanvas.getContext('2d');
        const scoreElement = document.getElementById('score');

        const BLOCK_SIZE = 30;
        const BOARD_WIDTH = 10;
        const BOARD_HEIGHT = 20;
        let score = 0;

        // 俄罗斯方块形状
        const SHAPES = [
            [[1, 1, 1, 1]], // I
            [[1, 1], [1, 1]], // O
            [[1, 1, 1], [0, 1, 0]], // T
            [[1, 1, 1], [1, 0, 0]], // L
            [[1, 1, 1], [0, 0, 1]], // J
            [[1, 1, 0], [0, 1, 1]], // S
            [[0, 1, 1], [1, 1, 0]]  // Z
        ];

        // 颜色配置
        const COLORS = [
            '#00f0f0', // cyan
            '#f0f000', // yellow
            '#a000f0', // purple
            '#f0a000', // orange
            '#0000f0', // blue
            '#00f000', // green
            '#f00000'  // red
        ];

        let board = Array(BOARD_HEIGHT).fill().map(() => Array(BOARD_WIDTH).fill(0));
        let currentPiece = null;
        let nextPiece = null;
        let currentX = 0;
        let currentY = 0;

        // 初始化游戏
        function init() {
            // 生成第一个方块
            nextPiece = {
                shape: SHAPES[Math.floor(Math.random() * SHAPES.length)],
                color: COLORS[Math.floor(Math.random() * COLORS.length)]
            };
            newPiece();
            
            // 游戏循环
            setInterval(() => {
                drop();
            }, 1000);

            // 键盘控制
            document.addEventListener('keydown', event => {
                switch(event.keyCode) {
                    case 37: // 左
                        move(-1);
                        break;
                    case 39: // 右
                        move(1);
                        break;
                    case 40: // 下
                        drop();
                        break;
                    case 38: // 上（旋转）
                        rotate();
                        break;
                }
            });
        }

        // 创建新方块
        function newPiece() {
            currentPiece = nextPiece;
            nextPiece = {
                shape: SHAPES[Math.floor(Math.random() * SHAPES.length)],
                color: COLORS[Math.floor(Math.random() * COLORS.length)]
            };
            currentX = Math.floor(BOARD_WIDTH/2) - Math.floor(currentPiece.shape[0].length/2);
            currentY = 0;
            
            // 绘制下一个方块
            drawNext();
        }

        // 绘制游戏板
        function draw() {
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // 绘制已固定的方块
            drawBoard();
            
            // 绘制当前方块
            drawPiece(currentX, currentY, currentPiece.shape, currentPiece.color);
        }

        // 方块下落
        function drop() {
            if (!collision(0, 1, currentPiece.shape)) {
                currentY++;
            } else {
                fixPiece();
                clearLines();
                newPiece();
            }
            draw();
        }

        // 碰撞检测
        function collision(offsetX, offsetY, shape) {
            for (let y = 0; y < shape.length; y++) {
                for (let x = 0; x < shape[y].length; x++) {
                    if (shape[y][x]) {
                        const newX = currentX + x + offsetX;
                        const newY = currentY + y + offsetY;
                        if (newX < 0 || newX >= BOARD_WIDTH || 
                            newY >= BOARD_HEIGHT ||
                            board[newY]?.[newX]) {
                            return true;
                        }
                    }
                }
            }
            return false;
        }

        // 其他辅助函数（移动、旋转、消行、计分等）...
        
        // 初始化游戏
        init();
    </script>
</body>
</html>
Commit message
