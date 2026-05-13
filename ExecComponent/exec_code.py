import os

class exec_code:
    """
    This class takes a string of code from AI prompt, creates a folder and a file
    like a project and execute the code
    """
    def __init__(self, code):
        self.code = code

    def __create_folder__(self, folder_name, isCreate=False):
        if not os.path.exists(folder_name) and isCreate:
            os.makedirs(folder_name)

    def __create_file__(self, file_name):
        with open(file_name, 'w') as f:
            f.write(self.code)

    def create_project_and_execute(self, folder_name, file_name, isCreate=False):
        if not isCreate:
            return
        
        # Find the path to test folder
        test_folder = os.path.join(os.getcwd(), 'test')
        if not os.path.exists(test_folder):
            os.makedirs(test_folder)

        # Each user will have different promt, create a folder for this user if not
        # First, retrieve the user name
        user_name = "user1"  # Replace with actual user name retrieval logic
        user_folder = os.path.join(test_folder, user_name)
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)

        # Each prompt will have different code, create a folder for this prompt if not
        # First, retrieve the prompt name
        prompt_name = "prompt1"  # Replace with actual prompt name retrieval logic
        self.__create_folder__(os.path.join(user_folder, prompt_name), isCreate=True)

        # Suppose the project has src, lib
        src_folder = os.path.join(user_folder, prompt_name, 'src')
        lib_folder = os.path.join(user_folder, prompt_name, 'lib')

        # Create a file in src folder and put the newly created code in this file
        self.__create_folder__(src_folder, isCreate=True)
        self.__create_folder__(lib_folder, isCreate=True)
        self.__create_file__(f"{src_folder}/{file_name}")

        # Finally, execute the code
        self.__execute__(src_folder, file_name)

    def __execute__(self, folder_name, file_name):
        #execute the code in the file
        file_path = os.path.join(folder_name, file_name)

        with open(file_path, 'r') as f:
            code = f.read()

        exec(code)