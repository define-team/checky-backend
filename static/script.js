document.getElementById("uploadBtn").onclick = async function () {
    const fileInput = document.getElementById("fileInput");
    const status = document.getElementById("status");

    if (!fileInput.files.length) {
        status.innerText = "Выберите PDF файл";
        return;
    }

    let formData = new FormData();
    formData.append("file", fileInput.files[0]);

    status.innerText = "Проверка...";

    let response = await fetch("/upload", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        status.innerText = "Ошибка!";
        return;
    }

    // создаём ссылку на загруженный PDF
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "checked.pdf";
    a.click();

    status.innerText = "Готово! Файл скачан.";
};
