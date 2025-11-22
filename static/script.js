document.addEventListener('DOMContentLoaded', () => {
  const addBtn = document.getElementById('add-question');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const questionsDiv = document.getElementById('questions');
      const count = questionsDiv.querySelectorAll('input').length + 1;
      const input = document.createElement('input');
      input.type = 'text';
      input.name = 'question';
      input.placeholder = `Question ${count}`;
      questionsDiv.appendChild(input);
    });
  }
});
